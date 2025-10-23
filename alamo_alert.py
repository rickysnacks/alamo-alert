# alamo_alert.py - Alamo Austin New Movies (Working - No Profile)
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# === CONFIG ===
EMAIL_SENDER = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_RECEIVER = "Eric.schnakenberg@gmail.com"
STATE_FILE = "/tmp/alamo_state.json"
CALENDAR_URL = "https://drafthouse.com/austin/calendar"

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")
    options.add_argument("--disable-javascript")  # Optional speed
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    options.binary_location = "/usr/bin/google-chrome"

    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def fetch_movies():
    driver = get_driver()
    try:
        print(f"[{datetime.now()}] Loading calendar...")
        driver.get(CALENDAR_URL)

        wait = WebDriverWait(driver, 15)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/film/']")))
            print("Movie links detected!")
        except:
            print("No /film/ links after 15s")

        time.sleep(3)

        movies = set()
        elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/film/']")
        for el in elements:
            title = el.text.strip()
            href = el.get_attribute("href") or ""
            if title and len(title) > 2 and "alamo" not in title.lower() and "/film/" in href:
                movies.add(title)

        print(f"Fetched {len(movies)} movies: {sorted(list(movies))[:6]}...")
        return sorted(list(movies))

    except Exception as e:
        print(f"Selenium error: {e}")
        return []
    finally:
        driver.quit()

def load_previous():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    return set()

空港def save_current(current):
    with open(STATE_FILE, "w") as f:
        json.dump(current, f)

def send_email(new_movies):
    if not new_movies: return
    subject = f"New Movie{'s' if len(new_movies)>1 else ''} at Alamo Austin!"
    body = "New movies:\n" + "\n".join(f"• {m}" for m in new_movies) + "\n\nhttps://drafthouse.com/austin/calendar"
    msg = MIMEMultipart()
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, EMAIL_RECEIVER, subject
    msg.attach(MIMEText(body, 'plain'))
    with smtplib.SMTP('smtp.gmail.com', 587) as s:
        s.starttls()
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s Lc.send_message(msg)
    print(f"Email sent: {len(new_movies)} new movies")

# === MAIN ===
print(f"[{datetime.now()}] Starting Alamo Austin check...")
current = fetch_movies()
previous = load_previous()
new = [m for m in current if m not in previous]

if new:
    send_email(new)
    print(f"NEW: {new}")
else:
    print("No new movies today.")
save_current(current)
print("Done.")
