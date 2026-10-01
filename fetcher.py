import io
import json
import os
import time
from datetime import date, datetime
import pdfplumber
from curl_cffi import requests as cffi_requests
from duckduckgo_search import DDGS

DATA_FILE = "data/announcements.json"

def extract_pdf_text(attachment_name):
    if not attachment_name:
        return None
    url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment_name}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    try:
        response = cffi_requests.get(url, headers=headers, impersonate="chrome", timeout=15)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:2])
        clean = text.strip()
        return clean if len(clean) > 30 else None
    except Exception as e:
        print(f"   -> PDF error: {e}")
        return None

def summarize_text(company_name, category, text):
    if not text:
        return "Attachment is a scanned image or contains no selectable text."

    clean_text = text[:3000].replace("\n", " ").strip()
    prompt = f"Summarize this corporate announcement for {company_name} ({category}) in 2 bullet points:\n{clean_text}"
    
    # Try up to 3 times using DuckDuckGo's anonymous AI chat
    for attempt in range(1, 4):
        try:
            with DDGS() as ddgs:
                # model options: "gpt-4o-mini" or "claude-3-haiku"
                response = ddgs.chat(prompt, model="gpt-4o-mini")
                if response:
                    return response.strip()
        except Exception as e:
            print(f"   -> AI attempt {attempt} failed: {e}")
            time.sleep(3)
            
    return "AI Summary unavailable (Network blocked by provider)."

def fetch_raw_bse_feed():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to BSE API...")
    today_str = date.today().strftime("%Y%m%d")
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
        return response.json().get("Table", [])
    except Exception as e:
        print(f"BSE API Error: {e}")
        return []

def run_once():
    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
            
    existing_ids = {item.get("NEWSID") for item in existing}
    raw_records = fetch_raw_bse_feed()
    new_count = 0

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(raw_records)} total filings for today.")

    for raw in raw_records[:10]:
        record_id = raw.get("NEWSID")
        if record_id not in existing_ids:
            print(f"Processing: {raw.get('SLONGNAME')}")
            
            pdf_text = extract_pdf_text(raw.get("ATTACHMENTNAME"))
            raw["summary"] = summarize_text(raw.get("SLONGNAME"), raw.get("NEWSSUB"), pdf_text)
            
            existing.append(raw)
            existing_ids.add(record_id)
            new_count += 1
            time.sleep(2) 

    if new_count > 0:
        existing.sort(key=lambda r: r.get("NEWS_DT") or "", reverse=True)
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(existing[:100], f, indent=2, ensure_ascii=False)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {new_count} new announcements.")

if __name__ == "__main__":
    run_once()
