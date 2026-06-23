import feedparser
import smtplib
import os
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- Configuration ---
# Update this if your feed has a specific XML path (e.g., /feed.xml or /index.xml)
FEED_URL = "https://osmanomics.github.io/my-rss-feed/.xml" 
RECIPIENT_EMAIL = "dylan.osmane@abbvie.com"

# These will be securely loaded from GitHub Secrets
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")

def main():
    print(f"Fetching RSS feed from {FEED_URL}...")
    feed = feedparser.parse(FEED_URL)
    
    recent_entries = []
    now = datetime.now(timezone.utc)
    
    # Filter entries from the last 7 days
    for entry in feed.entries:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            published_dt = datetime.fromtimestamp(time.mktime(entry.published_parsed), timezone.utc)
            if now - published_dt <= timedelta(days=7):
                recent_entries.append(entry)
                
    if not recent_entries:
        print("No new entries found for the past week. Exiting.")
        return

    print(f"Found {len(recent_entries)} entries from the past week. Preparing email...")
    
    # Build HTML email content
    subject = f"Weekly RSS Triage & Categorization ({now.strftime('%Y-%m-%d')})"
    body = """
    <html>
      <body style="font-family: Arial, sans-serif;">
        <h2>Past Week's Triage and Categorization</h2>
        <ul>
    """
    
    for entry in recent_entries:
        title = entry.title if hasattr(entry, 'title') else 'No Title'
        link = entry.link if hasattr(entry, 'link') else '#'
        published = entry.published if hasattr(entry, 'published') else 'Unknown Date'
        # Fetches tags/categories if your RSS feed provides them
        categories = ", ".join([tag.term for tag in entry.tags]) if hasattr(entry, 'tags') else 'Uncategorized'
        
        body += f"<li style='margin-bottom: 15px;'>"
        body += f"<a href='{link}' style='font-size: 16px; font-weight: bold;'>{title}</a><br>"
        body += f"<span style='color: #555;'><b>Date:</b> {published}</span><br>"
        body += f"<span style='color: #555;'><b>Category:</b> {categories}</span>"
        body += f"</li>"
    
    body += "</ul></body></html>"
    
    send_email(subject, body)

def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL

    msg.attach(MIMEText(html_body, "html"))

    # Connect to Gmail's SMTP server
    try:
        print("Connecting to SMTP server...")
        # If using a different provider, change 'smtp.gmail.com' and the port (465 for SSL)
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise # Ensures GitHub Actions registers the failure

if __name__ == "__main__":
    main()
