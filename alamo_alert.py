# alamo_alert.py - Alamo Austin New Movies (Final - Accurate Titles)
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
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
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    driver = webdriver.Chrome(options=options)
    return driver

def fetch_movies():
    driver = get_driver()
    try:
        print(f"[{datetime.now()}] Loading calendar...")
        driver.get(CALENDAR_URL)
        time.sleep(7)  # Let JS fully load

        movies = set()

        # TARGET: Only movie title elements in the calendar grid
        title_elements = driver.find_elements(By.CSS_SELECTOR, 
            "h3.CalendarFilmCard-filmTitle, "
            "a[data-testid='film-title'], "
            "div.CalendarFilmCard-filmTitle, "
            "h3 a"
        )

        for el in title_elements:
            title = el.text.strip()
            if (title and 
                len(title) > 2 and 
                title.upper() not in {"ALAMO DRAFTHOUSE", "CONTACT US", "TICKETS", "HOME", "SHOWTIMES"} and
                not title.startswith("Buy") and
                not title.startswith("View")):
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

def save_current(current):
    with open(STATE_FILE, "w") as f:
        json.dump(current, f)

def send_email(new_movies):
    if not new_movies: return
    subject = f"New Movie{'s' if len(new_movies)>1 else ''} at Alamo Austin!"
    body = "New movies just added:\n\n" + "\n".join(f"• {m}" for m in new_movies) + "\n\nhttps://drafthouse.com/austin/calendar"
    msg = MIMEMultipart()
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, EMAIL_RECEIVER, subject
    msg.attach(MIMEText(body, 'plain'))
    with smtplib.SMTP('smtp.gmail.com', 587) as s:
        s.starttls()
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s.send_message(msg)
    print(f"Email sent: {len(new_movies)} new movies")

# === MAIN ===
print(f"[{datetime.now()}] Starting Alamo Austin check...")
current = fetch_movies()
previous = load_previous()
new = [m for m in current if m not in previous]

if new:
    send_email(new)
    print(f"NEW MOVIES: {new}")
else:
    print("No new movies today.")
save_current(current)
print("Done.")
