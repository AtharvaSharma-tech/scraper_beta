import io
import json
import os
import time
from datetime import datetime, timedelta, timezone
import pdfplumber
from curl_cffi import requests as cffi_requests
from summarizer import summarize

DATA_FILE = "data/announcements.json"
MAX_PER_RUN = 10
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST)


def extract_pdf_text(attachment_name):
    if not attachment_name:
        return None
    url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment_name}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    try:
        response = cffi_requests.get(url, headers=headers, impersonate="chrome", timeout=15)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:3])
        return text.strip() if text else None
    except Exception as e:
        print(f"   -> PDF error: {e}")
        return None


def fetch_raw_bse_feed():
    print(f"[{now_ist().strftime('%H:%M:%S')} IST] Connecting to BSE API...")
    today_str = now_ist().strftime("%Y%m%d")
    url = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
    params = {
        "pageno": "1", "strCat": "-1", "strPrevDate": today_str,
        "strScrip": "", "strSearch": "P", "strToDate": today_str, "strType": "C"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Referer": "https://www.bseindia.com/"
    }
    try:
        response = cffi_requests.get(url, headers=headers, params=params, impersonate="chrome", timeout=15)
        response.raise_for_status()
        return response.json().get("Table", [])
    except Exception as e:
        print(f"BSE API Error: {e}")
        return []


def save(existing):
    existing.sort(key=lambda r: r.get("NEWS_DT") or "", reverse=True)
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing[:100], f, indent=2, ensure_ascii=False)


def run_once():
    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing_ids = {item.get("NEWSID") for item in existing}
    raw_records = fetch_raw_bse_feed()
    pending = [r for r in raw_records if r.get("NEWSID") and r["NEWSID"] not in existing_ids]
    print(f"{len(raw_records)} filings today, {len(pending)} unprocessed.")

    new_count, failures = 0, 0
    for raw in pending[:MAX_PER_RUN]:
        print(f"Processing: {raw.get('SLONGNAME')}")
        pdf_text = extract_pdf_text(raw.get("ATTACHMENTNAME"))

        if pdf_text:
            summary = summarize(raw.get("SLONGNAME"), raw.get("NEWSSUB"), pdf_text)
        else:
            summary = "* Attachment contains no selectable text or is a scanned image."

        if summary is None:  # AI failed: don't store, retry next run
            failures += 1
            if failures >= 3:
                print("Three AI failures, stopping this run.")
                break
            continue

        raw["summary"] = summary
        existing.append(raw)
        existing_ids.add(raw["NEWSID"])
        new_count += 1
        save(existing)  # incremental save so a crash doesn't lose progress
        time.sleep(4)

    print(f"Saved {new_count} new announcements.")


if __name__ == "__main__":
    print("fetcher.py started", flush=True)
    run_once()
