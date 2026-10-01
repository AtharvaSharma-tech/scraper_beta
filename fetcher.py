import io
import json
import logging
import os
import time
from datetime import date, datetime, timedelta
import pdfplumber
import requests
from bse import BSE

# Import the GPT4Free client (No accounts/API keys needed)
from g4f.client import Client

logging.getLogger("pdfminer").setLevel(logging.ERROR)
DATA_FILE = "data/announcements.json"
ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

# Initialize the free AI client
client = Client()

def extract_pdf_text(attachment_name):
    if not attachment_name:
        return None
    url = ATTACHMENT_BASE_URL + attachment_name
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:3])
        clean = text.strip()
        return clean if len(clean) > 30 else None
    except Exception as e:
        print(f"   -> PDF extraction note: {e}")
        return None


def summarize_text(company_name, category, text):
    if not text:
        return "Attachment is a scanned image or contains no selectable text."

    clean_text = text[:3500].replace("\n", " ").strip()
    prompt = (
        f"You are a financial analyst. Summarize this corporate announcement for {company_name} "
        f"({category}) in 2 clear bullet points focusing on key numbers, dates, or decisions:\n{clean_text}"
    )

    try:
        # Automatically routes to free ChatGPT/DuckDuckGo/Claude endpoints
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"   -> AI error: {e}")
        return "Summary temporarily delayed due to network traffic."


def load_existing():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_announcements(announcements):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(announcements, f, indent=2, ensure_ascii=False)


def fetch_latest():
    today = date.today()
    start_date = today - timedelta(days=2)
    with BSE(download_folder="./data") as bse:
        result = bse.announcements(page_no=1, from_date=start_date, to_date=today)
        return result.get("Table", [])


def run_once():
    existing = load_existing()
    existing_ids = {item.get("NEWSID") for item in existing}
    raw_records = fetch_latest()
    new_count = 0

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting scrape...")
    
    # Grab the top 20 items so the "Load Next 10" button has data to show
    for raw in raw_records[:20]:
        record_id = raw.get("NEWSID")
        if record_id not in existing_ids:
            print(f"Processing: {raw.get('SLONGNAME')}")
            pdf_text = extract_pdf_text(raw.get("ATTACHMENTNAME"))
            
            raw["summary"] = summarize_text(
                raw.get("SLONGNAME", "Company"),
                raw.get("NEWSSUB", "Filing"),
                pdf_text
            )
            
            existing.append(raw)
            existing_ids.add(record_id)
            new_count += 1
            time.sleep(1) 

    if new_count > 0:
        existing.sort(key=lambda r: r.get("NEWS_DT") or "", reverse=True)
        # Save up to 100 items to keep a deep backlog for the website
        save_announcements(existing[:100])

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {new_count} announcements.")


if __name__ == "__main__":
    run_once()
