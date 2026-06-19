import os
import json
import re
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
# AbbVie product portfolio (loaded once at startup from the Excel file)
# ---------------------------------------------------------------------------
def load_abbvie_products(path="AbbVie_Products.xlsx"):
    """Return a set of upper-cased product names from the AbbVie product list."""
    products = set()
    if not os.path.exists(path):
        print(f"Warning: {path} not found – product filter disabled.")
        return products
    try:
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        for row in ws.iter_rows(min_row=2):
            name = row[0].value
            if name:
                products.add(str(name).strip().upper())
    except Exception as e:
        print(f"Warning: could not load AbbVie products – {e}")
    return products

ABBVIE_PRODUCTS = load_abbvie_products()

# Pre-build a sorted list (longest names first) so multi-word brands match before
# any single-word sub-string within them (e.g. "REFRESH PLUS" before "REFRESH").
_ABBVIE_PRODUCTS_SORTED = sorted(ABBVIE_PRODUCTS, key=len, reverse=True)


def extract_mentioned_products(text):
    """Return the set of AbbVie product names found in *text* (case-insensitive)."""
    text_upper = text.upper()
    found = set()
    for product in _ABBVIE_PRODUCTS_SORTED:
        # Whole-word match so "FML" doesn't match inside "FMLA"
        pattern = r'\b' + re.escape(product) + r'\b'
        if re.search(pattern, text_upper):
            found.add(product)
    return found


def is_non_abbvie_product_mentioned(title, summary):
    """
    Return True when the text explicitly names a pharmaceutical product
    that is NOT in AbbVie's regulatory portfolio.

    Strategy:
      1. Ask the AI whether any specific drug/product name is mentioned.
      2. If yes, check whether any of those names appear in ABBVIE_PRODUCTS.
      3. If at least one named product is found and NONE of them are AbbVie
         products, classify as non-AbbVie and mark NOT TRACKED.
    """
    if not ABBVIE_PRODUCTS:
        # Safety: if the product list failed to load, skip this filter
        return False

    combined_text = f"{title} {summary}"

    # --- Step 1: quick local scan for known AbbVie product names -----------
    abbvie_hits = extract_mentioned_products(combined_text)
    if abbvie_hits:
        # An AbbVie product IS mentioned → do NOT override
        return False

    # --- Step 2: ask the AI if any specific product name is mentioned -------
    prompt = (
        "You are a pharmaceutical regulatory affairs expert.\n"
        "Read the following regulatory update and answer with ONLY a JSON object:\n"
        '  {"product_mentioned": true/false, "product_names": ["NAME1", ...]}\n'
        "Set product_mentioned=true if the text refers to a specific named drug, "
        "biologic, device brand, or active ingredient. "
        "Set it to false for generic guidance documents, policy updates, or process changes "
        "that do not target a specific product.\n"
        "Product names should be in UPPERCASE.\n\n"
        f"Title: {title}\nSummary: {summary}"
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a strict JSON-output AI. Reply ONLY with a valid JSON object."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0
    }
    try:
        response = requests.post(DEEPSEEK_ENDPOINT, headers=headers, json=payload, timeout=15)
        raw = response.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        result = json.loads(raw)
    except Exception as e:
        print(f"Product-filter API error: {e}")
        return False  # On any error, do not override

    if not result.get("product_mentioned", False):
        return False  # No specific product named → keep original classification

    # --- Step 3: check if any of the named products are AbbVie products ----
    named = [str(n).strip().upper() for n in result.get("product_names", [])]
    for name in named:
        # Also scan the product name itself in case the AI returned a substring
        if name in ABBVIE_PRODUCTS:
            return False
        # Fuzzy: check if an AbbVie product is mentioned within the AI's label
        for ap in ABBVIE_PRODUCTS:
            if ap in name or name in ap:
                return False
    # Product(s) mentioned but none are AbbVie → override to NOT TRACKED
    print(f"  -> Non-AbbVie product(s) detected: {named} – marking NOT TRACKED")
    return True

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

            # Pre-classification filter: Canada Gazette items are not tracked.
            if "canada gazette" in title.lower():
                print("  -> Canada Gazette item – marking NOT TRACKED")
                category = "Not tracked (Canada Gazette)"
                action = "Not tracked"
            else:
                category = classify_regulatory_update(title, summary)
                action = CATEGORY_MAPPING.get(category, "Manual Review")

                # Post-triage product filter: if a non-AbbVie product is explicitly
                # mentioned and none of AbbVie's products are referenced, override.
                if action != "Not tracked":  # skip items already categorised as not tracked
                    if is_non_abbvie_product_mentioned(title, summary):
                        category = "Not tracked (non-AbbVie product)"
                        action = "Not tracked"

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
