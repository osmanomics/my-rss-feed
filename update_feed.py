import os
import re
import json
import feedparser
import requests
import openpyxl
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

# ---------------------------------------------------------------------------
# AbbVie portfolio filter
# ---------------------------------------------------------------------------
ABBVIE_PORTFOLIO_FILE = "AbbVie_Products.xlsx"

# Dosage / unit tokens that are too generic to use as search terms
_SKIP_TOKENS = {
    "mg", "ml", "mcg", "unit", "vial", "syr", "g", "w/v",
    "mgs", "%", "and", "the", "or", "of", "in", "per",
}

def load_abbvie_portfolio(filepath: str = ABBVIE_PORTFOLIO_FILE) -> set:
    """Return a set of lowercase search terms from the AbbVie Health Canada portfolio.

    Includes:
    - Brand / product names (e.g. "humira", "rinvoq")
    - Individual meaningful words from active ingredient strings
      (e.g. "adalimumab", "upadacitinib"), skipping dosage tokens.
    """
    terms: set = set()
    if not os.path.exists(filepath):
        print(f"[WARNING] AbbVie portfolio file not found: {filepath}. "
              "AbbVie relevance filter will be DISABLED.")
        return terms  # empty set → filter disabled downstream

    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active
    first_row = True
    for row in ws.iter_rows(values_only=True):
        if first_row:          # skip header row
            first_row = False
            continue
        product_name, active_ingredients = row[0], row[1]
        # Add brand name
        if product_name:
            terms.add(product_name.strip().lower())
        # Add individual words from the active ingredient string
        if active_ingredients:
            for token in re.split(r'[\s,/()]+', active_ingredients):
                token = token.strip().lower()
                if token and token not in _SKIP_TOKENS and not re.fullmatch(r'[\d.]+', token):
                    terms.add(token)
    wb.close()
    return terms


ABBVIE_TERMS: set = load_abbvie_portfolio()


def is_abbvie_relevant(title: str, summary: str) -> bool:
    """Return True if the title or summary mentions an AbbVie product or ingredient.

    When ABBVIE_TERMS is empty (file missing), returns True so that the filter
    is effectively disabled and no items are incorrectly suppressed.
    """
    if not ABBVIE_TERMS:
        return True  # filter disabled – treat everything as potentially relevant

    text = (title + " " + summary).lower()
    # Tokenise the text once for fast set-intersection check
    text_tokens = set(re.split(r'[\s,/()\[\]\-]+', text))
    return bool(ABBVIE_TERMS & text_tokens)

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
            action = CATEGORY_MAPPING.get(category, "Manual Review")

            # --- AbbVie portfolio relevance check ----------------------------
            # If the update has no connection to AbbVie's Health Canada
            # portfolio (no product name or active ingredient match) it cannot
            # have a regulatory affairs impact on AbbVie and is filed as
            # NOT TRACKED, regardless of the regulatory category assigned above.
            abbvie_relevant = is_abbvie_relevant(title, summary)
            if not abbvie_relevant and action != "Not tracked":
                print(f"  → Not AbbVie-relevant. Overriding action to NOT TRACKED.")
                action = "NOT TRACKED"
            # -----------------------------------------------------------------

            new_items.append({
                "title": title,
                "link": link,
                "pubDate": entry.get('published', entry.get('updated', '')),
                "category": category,
                "action": action,
                "abbvie_relevant": abbvie_relevant
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
