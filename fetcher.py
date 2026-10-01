import io
import json
import logging
import os
import time
from datetime import date, datetime
import pdfplumber
import requests
from bse import BSE

# 1. Silence PDF font parser warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)

DATA_FILE = "data/announcements.json"
ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"


def extract_pdf_text(attachment_name):
    """Download the BSE PDF and extract text from the first 2 pages."""
    if not attachment_name:
        return None
    url = ATTACHMENT_BASE_URL + attachment_name
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:2])
        return text.strip()
    except Exception:
        return None


def summarize_text(company_name, category, text):
    """Summarize using a keyless, zero-login public AI endpoint (takes ~1-2 seconds)."""
    if not text:
        return "No attachment content available."

    clean_text = text[:3000].replace("\n", " ")
    prompt = (
        f"You are a financial analyst. Summarize this corporate announcement for {company_name} "
        f"({category}) in 2 brief bullet points focusing only on key numbers or decisions:\n{clean_text}"
    )

    try:
        # Keyless free endpoint - no account or token required
        response = requests.post(
            "https://text.pollinations.ai/",
            json={
                "messages": [{"role": "user", "content": prompt}],
                "model": "openai"
            },
            timeout=25
        )
        if response.status_code == 200:
            return response.text.strip()
    except Exception as e:
        print(f"Summary request failed: {e}")

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
    """Fetch only the latest page of today's announcements to stay fast."""
    today = date.today()
    with BSE(download_folder="./data") as bse:
        result = bse.announcements(page_no=1, from_date=today, to_date=today)
        return result.get("Table", [])


def run_once():
    existing = load_existing()
    existing_ids = {item.get("NEWSID") for item in existing}

    raw_records = fetch_latest()
    new_count = 0

    # Limit to the top 10 newest items per run
    for raw in raw_records[:10]:
        record_id = raw.get("NEWSID")
        if record_id not in existing_ids:
            print(f"Summarizing filing for: {raw.get('SLONGNAME')}")
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

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {new_count} new announcements.")


if __name__ == "__main__":
    run_once()
