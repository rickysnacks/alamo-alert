# alamo_alert.py - Alamo Drafthouse Austin New Release Alert (GitHub Actions)
import requests
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime

# === CONFIG ===
MARKET = "austin"
EMAIL_SENDER = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_RECEIVER = "Eric.schnakenberg@gmail.com"
STATE_FILE = "/tmp/alamo_state.json"  # GitHub uses /tmp

THEATERS_URL = "https://drafthouse.com/api/v1/theaters"
SHOWTIMES_URL = "https://drafthouse.com/api/v1/showtimes"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def get_austin_theater_ids():
    try:
        resp = requests.get(THEATERS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        theaters = resp.json()
        ids = [t["id"] for t in theaters if t.get("market", "").lower() == MARKET]
        print(f"Found {len(ids)} Austin theaters: {ids}")
        return ids or [1, 2, 3, 4, 5]  # fallback
    except Exception as e:
        print(f"Theaters failed: {e}")
        return [1, 2, 3, 4, 5]

def fetch_movies():
    ids = get_austin_theater_ids()
    try:
        resp = requests.get(SHOWTIMES_URL, headers=HEADERS, params={"theater_id": ",".join(map(str, ids))}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        movies = {item["film"]["title"].strip() for item in data.get("showtimes", []) if "title" in item.get("film", {})}
        print(f"Fetched {len(movies)} movies")
        return sorted(list(movies))
    except Exception as e:
        print(f"Showtimes failed: {e}")
        return []

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
    body = "New movies:\n" + "\n".join(f"• {m}" for m in new_movies) + "\n\nhttps://drafthouse.com/austin/calendar"
    msg = MIMEMultipart()
    msg['From'], msg['To'], msg['Subject'] = EMAIL_SENDER, EMAIL_RECEIVER, subject
    msg.attach(MIMEText(body, 'plain'))
    with smtplib.SMTP('smtp.gmail.com', 587) as s:
        s.starttls()
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s.send_message(msg)
    print(f"Email sent: {len(new_movies)} new movies")

# === MAIN ===
print(f"[{datetime.now()}] Starting check...")
current = fetch_movies()
previous = load_previous()
new = [m for m in current if m not in previous]
if new: send_email(new)
else: print("No new movies.")
save_current(current)
print("Done.")
