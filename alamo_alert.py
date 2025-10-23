#!/usr/bin/env python3
"""
Alamo Drafthouse Austin – New Movie Alert Script (2025)
Detects new movie titles added to Austin theaters and sends email alerts.
"""

import logging
import os
import json
import time
from datetime import datetime
from typing import List, Set

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

# ============================= CONFIG =============================
CALENDAR_URL = "https://drafthouse.com/austin?showCalendar=true"  # Calendar view for new movies
CACHE_FILE = "alamo_movie_cache.json"  # Caches movie titles
LOG_FILE = "alamo_alert.log"
DEBUG_SCREENSHOT = "debug_screenshot.png"

# Email via GitHub Secrets (set EMAIL_ENABLED to 'true' to activate)
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_TO = os.getenv("EMAIL_TO", "Eric.schnakenberg@gmail.com")
EMAIL_FROM = os.getenv("EMAIL_FROM", "alamo.alert.bot@gmail.com")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_SMTP = os.getenv("EMAIL_SMTP", "smtp.gmail.com:587")

# =================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_driver():
    """Initialize Chrome with CI-safe + anti-bot options."""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-browser-side-navigation')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    # Spoof real user agent
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
    )

    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
        driver.set_page_load_timeout(40)
        logger.info("WebDriver initialized with stealth.")
        return driver
    except Exception as e:
        logger.error(f"Failed to start WebDriver: {e}")
        raise


def fetch_movie_titles() -> Set[str]:
    """Scrape current movie titles from Alamo Austin calendar."""
    driver = get_driver()
    titles = set()

    try:
        logger.info("Fetching movie calendar from Alamo Drafthouse Austin...")
        driver.get(CALENDAR_URL)

        wait = WebDriverWait(driver, 30)

        # Wait for calendar grid or movie elements
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".CalendarGrid, .calendar-grid, [data-testid='calendar-grid'], .film-list")))
        logger.info("Calendar grid detected.")

        # Handle cookie banner
        try:
            accept = driver.find_element(
                By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')] | //button[contains(., 'OK')]"
            )
            accept.click()
            time.sleep(2)
            logger.info("Cookie banner accepted.")
        except:
            logger.info("No cookie banner.")

        # Scroll to load all movies (loop until no more changes)
        logger.info("Scrolling to load all movies...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        while scroll_attempts < 10:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_attempts += 1
        logger.info("Scroll complete.")

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Updated selectors for 2025 Alamo site
        movie_elements = soup.select("[data-testid='film-title'], .CalendarFilmCard-filmTitle, h3.film-title, a[href*='/film/'] h3, .film-card h3, .movie-title")

        logger.info(f"Found {len(movie_elements)} potential movie elements.")

        for el in movie_elements:
            title = el.get_text(strip=True)
            if title and len(title) > 2 and "alamo" not in title.lower() and "contact" not in title.lower():
                titles.add(title)

        logger.info(f"Filtered to {len(titles)} unique movie titles.")
        return titles

    except TimeoutException:
        logger.error("Timeout: Calendar did not load.")
    except Exception as e:
        logger.error(f"Scraping error: {e}")
    finally:
        # Save screenshot for debugging
        try:
            driver.save_screenshot(DEBUG_SCREENSHOT)
            logger.info(f"Screenshot saved: {DEBUG_SCREENSHOT}")
        except:
            pass
        driver.quit()

    return titles


def load_cache() -> Set[str]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()


def save_cache(titles: Set[str]):
    with open(CACHE_FILE, 'w') as f:
        json.dump(sorted(list(titles)), f, indent=2)


def get_new_movies(old: Set[str], new: Set[str]) -> List[str]:
    return sorted(list(new - old))


def send_email_alert(new_movies: List[str]):
    if not EMAIL_ENABLED or not all([EMAIL_TO, EMAIL_FROM, EMAIL_PASS]):
        logger.info("Email not enabled or credentials missing.")
        return

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    subject = f"New Movie{'s' if len(new_movies) > 1 else ''} Added at Alamo Austin!"
    body = "New movies just added to the Austin calendar:\n\n"
    for m in new_movies:
        body += f"• {m}\n"
    body += "\nCheck and buy tickets: " + CALENDAR_URL

    msg = MIMEMultipart()
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(EMAIL_SMTP)
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASS)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        logger.info("Email alert sent successfully.")
    except Exception as e:
        logger.error(f"Email send failed: {e}")


def main():
    logger.info("=== Alamo Austin New Movie Check ===")
    current_titles = fetch_movie_titles()
    previous_titles = load_cache()

    new_movies = get_new_movies(previous_titles, current_titles)

    if new_movies:
        logger.info(f"{len(new_movies)} new movie(s) found!")
        for m in new_movies:
            logger.info(f"NEW: {m}")
        send_email_alert(new_movies)
    else:
        logger.info("No new movies found.")

    save_cache(current_titles)
    logger.info("Check complete.\n")


if __name__ == "__main__":
    main()
