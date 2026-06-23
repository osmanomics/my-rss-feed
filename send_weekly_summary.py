def main():
    print(f"Fetching RSS feed from {FEED_URL}...")
    feed = feedparser.parse(FEED_URL)
    
    # Debugging information to see what feedparser actually downloaded
    print(f"Total entries found in feed: {len(feed.entries)}")
    
    if len(feed.entries) > 0:
        first = feed.entries[0]
        print("--- DEBUG: First Entry Data ---")
        print(f"Title: {first.get('title', 'No title found')}")
        print(f"Published (raw): {first.get('published', 'No published field')}")
        print(f"Updated (raw): {first.get('updated', 'No updated field')}")
        print("-------------------------------")
    
    recent_entries = []
    now = datetime.now(timezone.utc)
    
    # Filter entries from the last 7 days
    for entry in feed.entries:
        # Check for both 'published_parsed' (RSS) and 'updated_parsed' (Atom)
        parsed_time = entry.get('published_parsed') or entry.get('updated_parsed')
        
        if parsed_time:
            published_dt = datetime.fromtimestamp(time.mktime(parsed_time), timezone.utc)
            if now - published_dt <= timedelta(days=7):
                recent_entries.append(entry)
        else:
            print(f"Could not find a valid date for entry: {entry.get('title', 'Unknown')}")
                
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
        title = entry.get('title', 'No Title')
        link = entry.get('link', '#')
        
        # Grab whichever date is available for the email body
        published = entry.get('published') or entry.get('updated') or 'Unknown Date'
        
        categories = ", ".join([tag.term for tag in entry.tags]) if hasattr(entry, 'tags') else 'Uncategorized'
        
        body += f"<li style='margin-bottom: 15px;'>"
        body += f"<a href='{link}' style='font-size: 16px; font-weight: bold;'>{title}</a><br>"
        body += f"<span style='color: #555;'><b>Date:</b> {published}</span><br>"
        body += f"<span style='color: #555;'><b>Category:</b> {categories}</span>"
        body += f"</li>"
    
    body += "</ul></body></html>"
    
    send_email(subject, body)
