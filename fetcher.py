import io
import json
import logging
import os
import time
from datetime import date, datetime
import pdfplumber
import requests
from bse import BSE

# Silence PDF font warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)

DATA_FILE = "data/announcements.json"
ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"


def extract_pdf_text(attachment_name):
    if not attachment_name:
        return None
    url = ATTACHMENT_BASE_URL + attachment_name
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    print(f"   -> [{datetime.now().strftime('%H:%M:%S')}] Downloading PDF from BSE...")
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:2])
        print(f"   -> [{datetime.now().strftime('%H:%M:%S')}] PDF downloaded & read.")
        return text.strip()
    except Exception as e:
        print(f"   -> [{datetime.now().strftime('%H:%M:%S')}] PDF Error: {e}")
        return None


def summarize_text(company_name, category, text):
    if not text:
        return "No attachment content available."

    clean_text = text[:3000].replace("\n", " ")
    prompt = (
        f"You are a financial analyst. Summarize this corporate announcement for {company_name} "
        f"({category}) in 2 brief bullet points focusing only on key numbers or decisions:\n{clean_text}"
    )

    print(f"   -> [{datetime.now().strftime('%H:%M:%S')}] Sending to AI for summary...")
    try:
        response = requests.post(
            "https://text.pollinations.ai/",
            json={"messages": [{"role": "user", "content": prompt}], "model": "openai"},
            timeout=25
        )
        if response.status_code == 200:
            print(f"   -> [{datetime.now().strftime('%H:%M:%S')}] AI summary received.")
            return response.text.strip()
    except Exception as e:
        print(f"   -> [{datetime.now().strftime('%H:%M:%S')}] AI Error: {e}")
        
    return "Summary temporarily unavailable."


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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching today's announcement list from BSE...")
    today = date.today()
    with BSE(download_folder="./data") as bse:
        result = bse.announcements(page_no=1, from_date=today, to_date=today)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Announcement list fetched.")
        return result.get("Table", [])


def run_once():
    existing = load_existing()
    existing_ids = {item.get("NEWSID") for item in existing}

    raw_records = fetch_latest()
    new_count = 0

    # TESTING ONLY: Limit to the top 3 newest items so we can test speed
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting loop for top 3 filings...")
    for raw in raw_records[:3]:
        record_id = raw.get("NEWSID")
        if record_id not in existing_ids:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing: {raw.get('SLONGNAME')}")
            
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
        save_announcements(existing[:50])

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Saved {new_count} new announcements.")


if __name__ == "__main__":
    run_once()
