#!/usr/bin/env python3
"""
Alamo Drafthouse Austin – Movie Alert Script (2025)
Detects new showtimes and sends email alerts.
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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

# ============================= CONFIG =============================
THEATER_URL = "https://drafthouse.com/austin/showtimes"
CACHE>File = "alamo_cache.json"
LOG_FILE = "alamo_alert.log"

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
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
    )

    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver',', {get: () => false});")
        driver.set_page_load_timeout(30)
        logger.info("WebDriver initialized with stealth.")
        return driver
    except Exception as e:
        logger.error(f"Failed to start WebDriver: {e}")
        raise


def fetch_movies() -> List[Dict]:
    """Scrape current showtimes from Alamo Austin (2025 site)."""
    driver = get_driver()
    movies = []

    try:
        logger.info("Fetching showtimes from Alamo Drafthouse Austin...")
        driver.get(THEATER_URL)

        wait = WebDriverWait(driver, 20)

        # Wait for showtime grid
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='showtime-grid'], .showtimes-grid"))
        )
        logger.info("Showtime grid detected.")

        # Handle cookie banner
        try:
            accept = driver.find_element(
                By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"
            )
            accept.click()
            time.sleep(1)
            logger.info("Cookie banner accepted.")
        except:
            logger.info("No cookie banner.")

        # Scroll to trigger lazy load
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Try multiple possible movie card selectors
        movie_blocks = (
            soup.select("[data-testid='movie-card']") or
            soup.select(".movie-card") or
            soup.select("article") or
            soup.select(".showtime-movie")
        )

        logger.info(f"Found {len(movie_blocks)} movie blocks.")

        for block in movie_blocks:
            # Title
            title_elem = (
                block.select_one("[data-testid='movie-title']") or
                block.select_one("h3") or
                block.select_one("h2") or
                block.select_one(".movie-title")
            )
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            if not title:
                continue

            # Showtimes
            time_elems = (
                block.select("[data-testid='showtime-button']") or
                block.select(".showtime-button") or
                block.select("a[href*='session']") or
                block.select("button")
            )
            showtimes = [t.get_text(strip=True) for t in time_elems if t.get_text(strip=True)]

            if not showtimes:
                continue

            movies.append({
                "title": title,
                "showtimes": showtimes,
                "url": THEATER_URL
            })

        logger.info(f"Successfully parsed {len(movies)} movies with showtimes.")
        return movies

    except TimeoutException:
        logger.error("Timeout: Page did not load showtimes.")
    except Exception as e:
        logger.error(f"Scraping error: {e}")
    finally:
        # Save debug screenshot
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"debug_screenshot_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            logger.info(f"Screenshot saved: {screenshot_path}")
        except:
            pass
        driver.quit()

    return []


def load_cache() -> List[Dict]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def save_cache(movies: List[Dict]):
    with open(CACHE_FILE, 'w') as f:
        json.dump(movies, f, indent=2)


def get_new_showtimes(old: List[Dict], new: List[Dict]) -> List[Dict]:
    old_titles = {m["title"] for m in old}
    return [m for m in new if m["title"] not in old_titles]


def send_email_alert(new_movies: List[Dict]):
    if not EMAIL_ENABLED or not all([EMAIL_TO, EMAIL_FROM, EMAIL_PASS]):
        logger.info("Email not enabled or credentials missing.")
        return

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    subject = f"New Alamo Austin Showtime{'s' if len(new_movies) > 1 else ''}!"
    body = "New movies just dropped:\n\n"
    for m in new_movies:
        body += f"• {m['title']}\n"
        times = ', '.join(m['showtimes'][:5])
        if len(m['showtimes']) > 5:
            times += ' ...'
        body += f"  → {times}\n"
        body += f"  → {m['url']}\n\n"

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
        logger.info("No new movies found.")

    save_cache(current_movies)
    logger.info("Check complete.\n")


if __name__ == "__main__":
    main()
