import os
import json
import feedparser
import requests

RSS_URL = "https://osmanomics.github.io/my-rss-feed/feed.xml"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DATA_FILE = "data.json"

CATEGORY_MAPPING = {
    "CTA": "Track & assess", "Device/Drug Combo": "Track & assess", "Drug": "Track & assess",
    "HC Forms (RT-REP)": "Track & assess", "HC lists": "Track & assess", "ICH": "Track & assess",
    "MD (medical devices)": "Track & assess", "OTC": "Track & assess", "Reliance": "Track & assess",
    "Real World Evidence": "Track & assess", "Biosimilars Pharmacovigilence Related": "Track & assess",
    "DEL": "Track and inform", "MDEL": "Track and inform", "GMP": "Track and inform",
    "Cosmetics": "Track and inform", "Drug Supply": "Track and inform",
    "Health Care System": "Track and inform", "NHP": "Track and inform", "Vaccines": "Track and inform",
    "Food/Vitamin/Dietary Suplement": "Not tracked", "Narcotic": "Not tracked",
    "Nicotine": "Not tracked", "Veterinary": "Not tracked"
}
ALLOWED_CATEGORIES = list(CATEGORY_MAPPING.keys())

def load_existing_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def classify_regulatory_update(title, summary):
    prompt = f"""You are an expert regulatory affairs classifier for a pharmaceutical company.
Analyze the following regulatory update and categorize it into EXACTLY ONE of these categories: {ALLOWED_CATEGORIES}
Reply ONLY with the exact category name. No other text.

Title: {title}
Summary: {summary}"""

    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a strict data classification AI. You output only exact strings from a provided list."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0 
    }
    try:
        response = requests.post(DEEPSEEK_ENDPOINT, headers=headers, json=payload, timeout=15)
        ai_category = response.json()['choices'][0]['message']['content'].strip()
        return ai_category if ai_category in CATEGORY_MAPPING else "Unclassified"
    except Exception as e:
        print(f"API Error: {e}")
        return "Unclassified"

def main():
    existing_items = load_existing_data()
    # Create a quick lookup of existing titles or links to avoid re-processing and wasting API costs
    existing_links = {item['link'] for item in existing_items}
    
    feed = feedparser.parse(RSS_URL)
    new_items = []

    for entry in feed.entries:
        link = entry.get('link', '')
        if link in existing_links:
            continue  # Already processed in a past run
            
        title = entry.title
        summary = entry.get('summary', entry.get('description', ''))
        
        print(f"Processing new item: {title}")
        category = classify_regulatory_update(title, summary)
        action = CATEGORY_MAPPING.get(category, "Manual Review")
        
        new_items.append({
            "title": title,
            "link": link,
            "pubDate": entry.get('published', ''),
            "category": category,
            "action": action
        })
    
    # Prepend new items to the front of the archive
    updated_data = new_items + existing_items
    
    with open(DATA_FILE, 'w') as f:
        json.dump(updated_data, f, indent=2)
    print(f"Done! Added {len(new_items)} new items.")

if __name__ == "__main__":
    main()
