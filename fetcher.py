import io
import json
import logging
import os
import time
from datetime import date, datetime, timedelta
import pdfplumber
import requests
from bse import BSE

logging.getLogger("pdfminer").setLevel(logging.ERROR)

DATA_FILE = "data/announcements.json"
ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"


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

    # Retry up to 3 times with backoff if the public endpoint is busy
    for attempt in range(1, 4):
        try:
            response = requests.post(
                "https://text.pollinations.ai/",
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "model": "openai"
                },
                timeout=35
            )
            if response.status_code == 200 and response.text.strip():
                return response.text.strip()
            time.sleep(2 * attempt)
        except Exception:
            time.sleep(2 * attempt)

    return "Summary temporarily delayed due to high network traffic."


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

    # Process up to 5 newest announcements per run
    for raw in raw_records[:5]:
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
            time.sleep(2)  # Pause to avoid rate-limiting

    if new_count > 0:
        existing.sort(key=lambda r: r.get("NEWS_DT") or "", reverse=True)
        save_announcements(existing[:50])

    print(f"Saved {new_count} announcements.")


if __name__ == "__main__":
    run_once()
