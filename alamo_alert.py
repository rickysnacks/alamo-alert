# alamo_alert.py - Alamo Austin New Movies (Scraping Version)
import requests
from bs4 import BeautifulSoup
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime

# === CONFIG ===
EMAIL_SENDER = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_RECEIVER = "Eric.schnakenberg@gmail.com"
STATE_FILE = "/tmp/alamo_state.json"

CALENDAR_URL = "https://drafthouse.com/austin/calendar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def fetch_movies():
    try:
        resp = requests.get(CALENDAR_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        movies = set()
        
        # Extract titles from common Alamo classes (updated for 2025)
        for selector in [
            '.CalendarFilmCard-filmTitle',
            'h3.film-title',
            '.film-card h4',
            '.movie-title',
            'a[href*="/film/"]'
        ]:
            for item in soup.select(selector):
                title = item.get_text(strip=True)
                if title and len(title) > 2 and title not in movies:
                    movies.add(title)
        
        # Fallback: Parse JSON in script tags (Alamo embeds data)
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'Movie':
                            title = item.get('name')
                            if title:
                                movies.add(title)
            except:
                pass
        
        print(f"Fetched {len(movies)} movies: {sorted(list(movies))[:5]}...")
        return sorted(list(movies))
    
    except Exception as e:
        print(f"Scraping failed: {e}")
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
print(f"[{datetime.now()}] Starting Alamo Austin check...")
current = fetch_movies()
previous = load_previous()
new = [m for m in current if m not in previous]
if new:
    send_email(new)
    print(f"NEW: {new}")
else:
    print("No new movies.")
save_current(current)
print("Done.")
