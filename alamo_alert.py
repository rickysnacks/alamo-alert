#!/usr/bin/env python3
"""
Alamo Drafthouse Austin – Movie Alert Script
Detects new showtimes and sends notifications.
"""

import logging
import os
import json
import time
from datetime import datetime
from typing import List, Dict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

# ============================= CONFIG =============================
THEATER_URL = "https://drafthouse.com/austin/showtimes"
CACHE_FILE = "alamo_cache.json"
LOG_FILE = "alamo_alert.log"

# Optional: Set via GitHub Secrets
EMAIL_ENABLED = bool(os.getenv("EMAIL_ENABLED", "false").lower() == "true")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")
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
    """Initialize Chrome with CI-safe headless options."""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-browser-side-navigation')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    try:
        driver = webdriver.Chrome(options=options)  # Selenium Manager auto-downloads driver
        driver.set_page_load_timeout(30)
        logger.info("WebDriver initialized successfully.")
        return driver
    except Exception as e:
        logger.error(f"Failed to start WebDriver: {e}")
        raise


def fetch_movies() -> List[Dict]:
    """Scrape current showtimes from Alamo Austin."""
    driver = get_driver()
    try:
        logger.info("Fetching showtimes from Alamo Drafthouse Austin...")
        driver.get(THEATER_URL)
        time.sleep(5)  # Let JS load

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        movies = []

        # Adjust selectors based on actual site structure
        for movie_block in soup.select('.movie-listing'):
            title = movie_block.select_one('.movie-title')
            showtimes = movie_block.select('.showtime-button')

            if not title:
                continue

            movie_data = {
                "title": title.get_text(strip=True),
                "showtimes": [
                    st.get_text(strip=True) for st in showtimes
                ],
                "url": THEATER_URL
            }
            movies.append(movie_data)

        logger.info(f"Found {len(movies)} movies.")
        return movies

    except TimeoutException:
        logger.error("Page load timed out.")
        return []
    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        return []
    finally:
        driver.quit()


def load_cache() -> List[Dict]:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return []


def save_cache(movies: List[Dict]):
    with open(CACHE_FILE, 'w') as f:
        json.dump(movies, f, indent=2)


def get_new_showtimes(old: List[Dict], new: List[Dict]) -> List[Dict]:
    """Compare and return only new/updated entries."""
    old_titles = {m["title"] for m in old}
    return [m for m in new if m["title"] not in old_titles]


def send_email_alert(new_movies: List[Dict]):
    if not EMAIL_ENABLED or not all([EMAIL_TO, EMAIL_FROM, EMAIL_PASS]):
        logger.info("Email not configured. Skipping alert.")
        return

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    subject = f"New Alamo Austin Showtime{'s' if len(new_movies) > 1 else ''}!"
    body = "New movies detected:\n\n"
    for m in new_movies:
        body += f"• {m['title']}\n"
        if m['showtimes']:
            body += f"   Times: {', '.join(m['showtimes'][:3])}{'...' if len(m['showtimes']) > 3 else ''}\n"
        body += f"   → {m['url']}\n\n"

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
        logger.info("Email alert sent.")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def main():
    logger.info("=== Alamo Austin Alert Check ===")
    current_movies = fetch_movies()
    previous_movies = load_cache()

    new_movies = get_new_showtimes(previous_movies, current_movies)

    if new_movies:
        logger.info(f"{len(new_movies)} new movie(s) found!")
        for m in new_movies:
            logger.info(f"NEW: {m['title']} – {len(m['showtimes'])} showtimes")
        send_email_alert(new_movies)
    else:
        logger.info("No new movies.")

    save_cache(current_movies)
    logger.info("Check complete.\n")


if __name__ == "__main__":
    main()
