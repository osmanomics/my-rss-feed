import os
import json
import feedparser
import requests
from email.utils import parsedate_to_datetime
from datetime import datetime

RSS_URLS = [
    "https://www.canada.ca/content/dam/hc-sc/migration/hc-sc/rss/dhp-mps/drugs-drogues-eng.xml",
    "https://www.gazette.gc.ca/rss/p2-eng.xml",
    "https://www.gazette.gc.ca/rss/p1-eng.xml",
    "https://www.canada.ca/content/dam/hc-sc/migration/hc-sc/rss/dhp-mps/devices-instruments-eng.xml",
    "https://www.canada.ca/content/dam/hc-sc/migration/hc-sc/rss/dhp-mps/nhp-psn-eng.xml",
    "https://www.canada.ca/content/dam/hc-sc/migration/hc-sc/rss/dhp-mps/nhpid-bdipsn-eng.xml",
    "https://www.canada.ca/content/dam/hc-sc/migration/hc-sc/rss/dhp-mps/new-neuf-eng.xml",
    "https://www.canada.ca/content/dam/hc-sc/migration/hc-sc/rss/dhp-mps/compli-conform-eng.xml",
    "https://www.canada.ca/content/dam/hc-sc/migration/hc-sc/rss/dhp-mps/prod-eng.xml"
]
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DATA_FILE = "data.json"

# Sentinel value returned by the AI when the update has no RA impact on AbbVie
NOT_ABBVIE_RELEVANT = "NOT_ABBVIE_RELEVANT"

CATEGORY_MAPPING = {
    "CTA": "Track & assess", "Device/Drug Combo": "Track & assess", "Drug": "Track & assess",
    "HC Forms (RT-REP)": "Track & assess", "HC lists": "Track & assess", "ICH": "Track & assess",
    "MD (medical devices)": "Track & assess", "OTC": "Track & assess", "Reliance": "Track & assess",
    "Real World Evidence": "Track & assess", "Biosimilars Pharmacovigilence Related": "Not tracked",
    "DEL": "Track and inform", "MDEL": "Track and inform", "GMP": "Track and inform",
    "Cosmetics": "Track and inform", "Drug Supply": "Track and inform",
    "Health Care System": "Track and inform", "NHP": "Track and inform", "Vaccines": "Track and inform",
    "Food/Vitamin/Dietary Suplement": "Not tracked", "Narcotic": "Not tracked",
    "Nicotine": "Not tracked", "Veterinary": "Not tracked",
    # Auto-mapped sentinel for updates that don't affect AbbVie from an RA standpoint
    NOT_ABBVIE_RELEVANT: "Not tracked"
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
    """
    Classifies a regulatory update into one of the known categories.

    Step 1 – AbbVie relevance gate:
      AbbVie is a research-based biopharmaceutical company whose Canadian
      regulatory affairs scope covers prescription drugs, biologics,
      biosimilars, combination drug/device products, and clinical trials.
      If the update has NO regulatory affairs impact on AbbVie's portfolio
      (e.g. it concerns food, natural health products, cosmetics, veterinary
      products, narcotics, nicotine/tobacco, or other areas outside AbbVie's
      business), the model returns the sentinel NOT_ABBVIE_RELEVANT and the
      item is automatically placed in "Not tracked".

    Step 2 – Category classification (only if AbbVie-relevant):
      The model picks exactly one category from ALLOWED_CATEGORIES.
    """
    prompt = f"""You are an expert regulatory affairs classifier for AbbVie, a research-based biopharmaceutical company.
AbbVie's Canadian regulatory affairs scope covers: prescription drugs, biologics, biosimilars, combination drug/device products, clinical trials (CTAs), and directly related regulatory frameworks (ICH guidelines, GMP, real-world evidence, etc.).

STEP 1 – AbbVie relevance check:
Does this regulatory update have any impact on AbbVie from a regulatory affairs standpoint?
If NO (e.g. the update is about food, natural health products, cosmetics, veterinary products, narcotics, nicotine/tobacco, or any other area clearly outside AbbVie's business), reply with exactly: {NOT_ABBVIE_RELEVANT}

STEP 2 – If YES, classify into EXACTLY ONE of these categories: {ALLOWED_CATEGORIES}
Reply ONLY with the exact category name. No explanation, no extra text.

Title: {title}
Summary: {summary}"""

    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a strict regulatory affairs classification AI for AbbVie. You output only exact strings from a provided list. Never add explanations."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0
    }
    try:
        response = requests.post(DEEPSEEK_ENDPOINT, headers=headers, json=payload, timeout=15)
        ai_category = response.json()['choices'][0]['message']['content'].strip()
        if ai_category in CATEGORY_MAPPING:
            return ai_category
        # If the model returned something unexpected, default to Not tracked
        print(f"  Unexpected AI response '{ai_category}' – defaulting to NOT_ABBVIE_RELEVANT")
        return NOT_ABBVIE_RELEVANT
    except Exception as e:
        print(f"API Error: {e}")
        return NOT_ABBVIE_RELEVANT

def parse_date(date_str):
    if not date_str:
        return datetime.min
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.replace(tzinfo=None)
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).replace(tzinfo=None)
        except:
            return datetime.min

def main():
    existing_items = load_existing_data()
    # Create a quick lookup of existing titles or links to avoid re-processing and wasting API costs
    existing_links = {item['link'] for item in existing_items}
    
    new_items = []

    for url in RSS_URLS:
        print(f"Fetching {url}...")
        feed = feedparser.parse(url)

        for entry in feed.entries:
            link = entry.get('link', '')
            if link in existing_links:
                continue  # Already processed in a past run
                
            title = entry.title
            summary = entry.get('summary', entry.get('description', ''))
            
            print(f"Processing new item: {title}")
            category = classify_regulatory_update(title, summary)
            action = CATEGORY_MAPPING.get(category, "Not tracked")
            
            new_items.append({
                "title": title,
                "link": link,
                "pubDate": entry.get('published', entry.get('updated', '')),
                "category": category,
                "action": action
            })
    
    # Prepend new items to the front of the archive
    updated_data = new_items + existing_items
    
    # Sort chronologically, latest release at the top
    updated_data.sort(key=lambda x: parse_date(x.get('pubDate', '')), reverse=True)
    
    with open(DATA_FILE, 'w') as f:
        json.dump(updated_data, f, indent=2)
    print(f"Done! Added {len(new_items)} new items.")

if __name__ == "__main__":
    main()
