import json
import smtplib
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- Configuration ---
# --- Configuration ---
DATA_FILE = "data.json"
RECIPIENT_EMAILS = [
    
    "annie.chicoine@abbvie.com",
    "judith.mergl@abbvie.com",
    "navjotkaur.jaswal@abbvie.com"
]


# These will be securely loaded from GitHub Secrets
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")

def parse_date(date_str):
    """Reusing the robust date parser from your main code."""
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = parsedate_to_datetime(date_str)
        # Make sure the datetime is timezone-aware for the 7-day math
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except:
            return datetime.min.replace(tzinfo=timezone.utc)

def main():
    print(f"Loading categorized data from {DATA_FILE}...")
    
    if not os.path.exists(DATA_FILE):
        print(f"Error: {DATA_FILE} not found. Ensure your main code has run and saved the file.")
        return

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            all_items = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Could not decode {DATA_FILE}. Exiting.")
            return
            
    recent_entries = []
    now = datetime.now(timezone.utc)
    
    # Filter entries from the last 7 days
    for item in all_items:
        pub_date_str = item.get('pubDate', '')
        published_dt = parse_date(pub_date_str)
        
        if now - published_dt <= timedelta(days=7):
            recent_entries.append(item)
            
    if not recent_entries:
        print("No new entries found for the past week in data.json. Exiting.")
        return

    print(f"Found {len(recent_entries)} entries from the past week. Preparing email...")
    
    # Build HTML email content
    subject = f"Weekly Regulatory Triage & Categorization ({now.strftime('%Y-%m-%d')})"
    body = """
    <html>
      <body style="font-family: Arial, sans-serif;">
        <h2>Past Week's Regulatory Updates</h2>
        <ul>
    """
    
    for entry in recent_entries:
        title = entry.get('title', 'No Title')
        link = entry.get('link', '#')
        published = entry.get('pubDate', 'Unknown Date')
        category = entry.get('category', 'Unclassified')
        action = entry.get('action', 'Manual Review')
        
        # Color coding the action to make it easier to read
        action_color = "#D32F2F" if action == "Not tracked" else "#005A9C"

        body += f"<li style='margin-bottom: 20px;'>"
        body += f"<a href='{link}' style='font-size: 16px; font-weight: bold;'>{title}</a><br>"
        body += f"<span style='color: #555;'><b>Date:</b> {published}</span><br>"
        body += f"<span style='color: #555;'><b>Category:</b> {category}</span><br>"
        body += f"<span style='color: {action_color};'><b>Action:</b> {action}</span>"
        body += f"</li>"
    
    body += "</ul></body></html>"
    
    send_email(subject, body)

def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    
    # Joins the list of emails into a single comma-separated string for the header
    msg["To"] = ", ".join(RECIPIENT_EMAILS)

    msg.attach(MIMEText(html_body, "html"))

    # Connect to Gmail's SMTP server
    try:
        print(f"Connecting to SMTP server to send to {len(RECIPIENT_EMAILS)} recipients...")
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        # Pass the list of RECIPIENT_EMAILS to the sendmail function
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS, msg.as_string())
        server.quit()
        print("Email sent successfully to all recipients!")
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise # Ensures GitHub Actions registers the failure

        raise # Ensures GitHub Actions registers the failure

if __name__ == "__main__":
    main()
