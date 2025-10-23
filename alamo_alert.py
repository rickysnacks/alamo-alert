#!/usr/bin/env python3
"""
Alamo Drafthouse Austin – New Movie Alert (2025)
Detects NEW MOVIE TITLES from calendar table – crash-proof.
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
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, NoSuchElementException
)
from bs4 import BeautifulSoup

# ============================= CONFIG =============================
URL = "https://drafthouse.com/austin?showCalendar=true"
CACHE_FILE = "alamo_movie_cache.json"
LOG_FILE = "alamo_alert.log"
SCREENSHOT = "debug_calendar.png"

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
    opts.add_argument("--window-size=1400,1200")  # Smaller = less RAM
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-images")  # Speed + memory
    opts.add_argument("--disable-javascript")  # No, wait — we NEED JS
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
    driver.set_page_load_timeout(30)
    log.info("Driver initialized")
    return driver


def wait_for_calendar(driver):
    log.info("Waiting for calendar table...")
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
    )
    log.info("Calendar table found")


def click_load_more(driver):
    """Click 'Load More' if exists."""
    loaded = 0
    while True:
        try:
            btn = driver.find_element(By.XPATH, "//button[contains(., 'Load More')]")
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            driver.execute_script("arguments[0].click();", btn)
            log.info("Clicked Load More")
            time.sleep(3)
            loaded += 1
        except NoSuchElementException:
            log.info(f"Load More clicked {loaded} time(s)")
            break
        except Exception as e:
            log.warning(f"Load More failed: {e}")
            break


def scroll_gently(driver):
    """Scroll in small steps to avoid crash."""
    log.info("Scrolling gently...")
    for _ in range(8):
        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(1.5)
    log.info("Gentle scroll complete")


def fetch_movie_titles() -> Set[str]:
    driver = None
    titles: Set[str] = set()
    try:
        driver = get_driver()
        log.info(f"Loading: {URL}")
        driver.get(URL)
        time.sleep(5)

        wait_for_calendar(driver)
        click_load_more(driver)
        scroll_gently(driver)

        # Final wait for cells
        WebDriverWait(driver, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "table td a")) > 10
        )

        driver.save_screenshot(SCREENSHOT)
        log.info(f"Screenshot: {SCREENSHOT}")

        soup = BeautifulSoup(driver.page_source, "html.parser")
        links = soup.select("table td a[href*='/film/']")

        log.info(f"Found {len(links)} film links")

        for a in links:
            txt = a.get_text(strip=True)
            if txt and len(txt) > 3 and "alamo" not in txt.lower():
                titles.add(txt)

        log.info(f"Extracted {len(titles)} unique titles: {', '.join(sorted(titles)[:5])}{'...' if len(titles)>5 else ''}")
        return titles

    except Exception as e:
        log.error(f"SCRAPING FAILED: {e}")
        if driver:
            driver.save_screenshot(f"crash_{int(time.time())}.png")
        return titles
    finally:
        if driver:
            driver.quit()


# === CACHE & ALERT ===
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


def send_email(new: List[str]):
    if not EMAIL_ENABLED or not all([EMAIL_TO, EMAIL_FROM, EMAIL_PASS]):
        return
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = f"NEW MOVIE: {', '.join(new)}"
    body = "New in Austin:\n\n" + "\n".join(f"• {t}" for t in new) + f"\n\n{URL}"
    msg.attach(MIMEText(body, "plain"))

    try:
        s = smtplib.SMTP(*EMAIL_SMTP.split(":"))
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
    prev = load_cache()
    new = sorted(current - prev)

    if new:
        log.info(f"NEW: {', '.join(new)}")
        send_email(new)
    else:
        log.info("No new movies")

    save_cache(current)
    log.info("Done\n")


if __name__ == "__main__":
    main()
