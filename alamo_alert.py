#!/usr/bin/env python3
"""
Alamo Drafthouse Austin – New Movie Alert (2025)
Detects *new movie titles* (not show-times) and emails you instantly.
"""

import logging
import os
import json
import time
from datetime import datetime
from typing import Set, List

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

# ============================= CONFIG =============================
BASE_URL = "https://drafthouse.com/austin"
CALENDAR_URL = f"{BASE_URL}?showCalendar=true"
CACHE_FILE = "alamo_movie_cache.json"
LOG_FILE = "alamo_alert.log"
SCREENSHOT = "debug_calendar.png"

# Email – set EMAIL_ENABLED=true in GitHub Secrets to turn on
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_SMTP = os.getenv("SMTP_SERVER", "smtp.gmail.com:587")

# =================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger(__name__)


def get_driver() -> webdriver.Chrome:
    """CI-safe headless Chrome with anti-bot tricks."""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
    driver.set_page_load_timeout(40)
    log.info("Chrome driver ready")
    return driver


def click_calendar_view(driver) -> None:
    """Make sure the calendar tab, not the “show-times” grid, is displayed."""
    try:
        # The toggle is a button with text “Calendar View”
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(., 'Calendar View') or contains(., 'CALENDAR VIEW')]")
            )
        )
        driver.execute_script("arguments[0].click();", btn)
        log.info("Clicked Calendar View")
        time.sleep(2)
    except TimeoutException:
        log.info("Calendar View already active or not found – proceeding")


def accept_cookies(driver) -> None:
    """Dismiss the cookie banner if present."""
    try:
        btn = driver.find_element(
            By.XPATH,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') "
            "or contains(., 'OK') or contains(., 'Got it')]"
        )
        driver.execute_script("arguments[0].click();", btn)
        log.info("Cookie banner dismissed")
        time.sleep(2)
    except NoSuchElementException:
        log.info("No cookie banner")


def scroll_to_load_all(driver) -> None:
    """Scroll until the page height stops growing (lazy-load)."""
    log.info("Scrolling to load every film...")
    last_h = driver.execute_script("return document.body.scrollHeight")
    attempts = 0
    while attempts < 12:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        new_h = driver.execute_script("return document.body.scrollHeight")
        if new_h == last_h:
            break
        last_h = new_h
        attempts += 1
    log.info(f"Scrolling finished after {attempts} steps")


def fetch_movie_titles() -> Set[str]:
    """Return a set of all unique movie titles currently listed."""
    driver = get_driver()
    titles: Set[str] = set()

    try:
        log.info(f"Opening calendar → {CALENDAR_URL}")
        driver.get(CALENDAR_URL)

        # 1. Ensure calendar view
        click_calendar_view(driver)

        # 2. Cookie banner
        accept_cookies(driver)

        # 3. Wait for the calendar grid
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".CalendarGrid, .calendar-grid"))
        )
        log.info("Calendar grid present")

        # 4. Load everything
        scroll_to_load_all(driver)

        # 5. Parse with BS4
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # ----- SELECTORS THAT WORK ON THE 2025 SITE -----
        candidates = (
            soup.select("[data-testid='film-title']") or
            soup.select(".CalendarFilmCard-filmTitle") or
            soup.select(".film-card h3") or
            soup.select("a[href*='/film/'] h3") or
            soup.select(".movie-title")
        )
        log.info(f"Found {len(candidates)} candidate elements")

        for el in candidates:
            txt = el.get_text(strip=True)
            if txt and len(txt) > 2 and "alamo" not in txt.lower():
                titles.add(txt)

        log.info(f"Extracted {len(titles)} unique movie titles")
        return titles

    except Exception as e:
        log.error(f"Scraping failed: {e}")
        return titles
    finally:
        driver.save_screenshot(SCREENSHOT)
        log.info(f"Screenshot → {SCREENSHOT}")
        driver.quit()


# ---------- CACHE ----------
def load_cache() -> Set[str]:
    if not os.path.exists(CACHE_FILE):
        return set()
    try:
        with open(CACHE_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_cache(titles: Set[str]) -> None:
    with open(CACHE_FILE, "w") as f:
        json.dump(sorted(titles), f, indent=2)


# ---------- ALERT ----------
def send_email(new_titles: List[str]) -> None:
    if not EMAIL_ENABLED or not all([EMAIL_TO, EMAIL_FROM, EMAIL_PASS]):
        log.info("Email disabled or missing creds")
        return

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    subject = f"New Movie{'s' if len(new_titles) > 1 else ''} at Alamo Austin!"
    body = "New titles just appeared:\n\n"
    for t in new_titles:
        body += f"• {t}\n"
    body += f"\nBuy tickets fast → {CALENDAR_URL}"

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        srv = smtplib.SMTP(EMAIL_SMTP.split(":")[0], int(EMAIL_SMTP.split(":")[1]))
        srv.starttls()
        srv.login(EMAIL_FROM, EMAIL_PASS)
        srv.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        srv.quit()
        log.info("Email sent")
    except Exception as e:
        log.error(f"Email error: {e}")


# ---------- MAIN ----------
def main() -> None:
    log.info("=== Alamo New-Movie Check ===")
    current = fetch_movie_titles()
    previous = load_cache()

    new = sorted(current - previous)
    if new:
        log.info(f"{len(new)} NEW MOVIE(S): {', '.join(new)}")
        send_email(new)
    else:
        log.info("No new movies")

    save_cache(current)
    log.info("Run finished\n")


if __name__ == "__main__":
    main()
