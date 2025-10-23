#!/usr/bin/env python3
"""
Alamo Drafthouse Austin – New Movie Alert (2025)
Detects NEW MOVIE TITLES from the calendar table.
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
url = f"{BASE_URL}?showCalendar=true"
CACHE_FILE = "alamo_movie_cache.json"
LOG_FILE = "alamo_alert.log"
SCREENSHOT = "debug_calendar_full.png"

# Email via GitHub Secrets
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_SMTP = os.getenv("EMAIL_SMTP", "smtp.gmail.com:587")

# =================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger(__name__)


def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1600")  # Taller window
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
    driver.set_page_load_timeout(45)
    log.info("Driver ready")
    return driver


def accept_cookies(driver):
    try:
        btn = driver.find_element(
            By.XPATH,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') "
            "or contains(., 'OK')]"
        )
        driver.execute_script("arguments[0].click();", btn)
        log.info("Cookies accepted")
        time.sleep(2)
    except:
        log.info("No cookie banner")


def click_calendar_view(driver):
    try:
        toggle = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(., 'Calendar View')] | //span[contains(., 'Calendar View')]")
            )
        )
        driver.execute_script("arguments[0].click();", toggle)
        log.info("Switched to Calendar View")
        time.sleep(3)
    except:
        log.info("Already in Calendar View")


def scroll_to_load_calendar(driver):
    """Scroll until all calendar rows are loaded."""
    log.info("Scrolling to load full calendar...")
    last_height = 0
    stable_count = 0
    max_stable = 5

    while stable_count < max_stable:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        # Wait for new rows to appear
        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "table.calendar td")) > 50
            )
        except:
            pass

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            stable_count += 1
        else:
            stable_count = 0
        last_height = new_height

    log.info("Calendar fully loaded")


def fetch_movie_titles() -> Set[str]:
    driver = get_driver()
    titles: Set[str] = set()

    try:
        log.info(f"Loading calendar: {url}")
        driver.get(url)

        accept_cookies(driver)
        click_calendar_view(driver)

        # Wait for calendar table
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.calendar, .CalendarGrid"))
        )
        log.info("Calendar table detected")

        scroll_to_load_calendar(driver)

        # Take full-page screenshot
        driver.save_screenshot(SCREENSHOT)
        log.info(f"Full screenshot saved: {SCREENSHOT}")

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Extract titles from <td> in calendar
        cells = soup.select("table.calendar td, .CalendarGrid td, td")
        log.info(f"Found {len(cells)} calendar cells")

        for cell in cells:
            # Look for links with movie titles
            link = cell.find("a", href=True)
            if not link:
                continue
            title = link.get_text(strip=True)
            if title and len(title) > 3 and "alamo" not in title.lower():
                titles.add(title)

        log.info(f"Extracted {len(titles)} unique movie titles")
        return titles

    except Exception as e:
        log.error(f"Error: {e}")
        driver.save_screenshot(f"error_{int(time.time())}.png")
        return titles
    finally:
        driver.quit()


# === Cache & Alert ===
def load_cache() -> Set[str]:
    if not os.path.exists(CACHE_FILE):
        return set()
    try:
        with open(CACHE_FILE) as f:
            return set(json.load(f))
    except:
        return set()


def save_cache(titles: Set[str]):
    with open(CACHE_FILE, "w") as f:
        json.dump(sorted(titles), f, indent=2)


def send_email(new_titles: List[str]):
    if not EMAIL_ENABLED or not all([EMAIL_TO, EMAIL_FROM, EMAIL_PASS]):
        log.info("Email not enabled")
        return

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    subject = f"NEW MOVIE ALERT: {len(new_titles)} title{'s' if len(new_titles)>1 else ''}"
    body = "New movies added to Alamo Austin:\n\n"
    for t in new_titles:
        body += f"• {t}\n"
    body += f"\n→ {url}"

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        s = smtplib.SMTP(EMAIL_SMTP.split(":")[0], int(EMAIL_SMTP.split(":")[1]))
        s.starttls()
        s.login(EMAIL_FROM, EMAIL_PASS)
        s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        s.quit()
        log.info("Email sent")
    except Exception as e:
        log.error(f"Email failed: {e}")


def main():
    log.info("=== Alamo New Movie Check ===")
    current = fetch_movie_titles()
    previous = load_cache()
    new = sorted(current - previous)

    if new:
        log.info(f"NEW: {', '.join(new)}")
        send_email(new)
    else:
        log.info("No new movies")

    save_cache(current)
    log.info("Done\n")


if __name__ == "__main__":
    main()
