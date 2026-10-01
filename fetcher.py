import io
import json
import os
import time
from datetime import date, datetime
import pdfplumber
from curl_cffi import requests as cffi_requests
from google import genai

DATA_FILE = "data/announcements.json"

# Initialize the official Gemini client using the secure GitHub Secret
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

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

def summarize_text(company_name, category, text):
    if not text:
        return "* Attachment contains no selectable text or is a scanned image."

    clean_text = text[:4000].replace("\n", " ").strip()
    prompt = (
        f"You are a financial analyst. Summarize this corporate announcement for {company_name} "
        f"({category}) in 2 clear bullet points focusing on key numbers, dates, or financial decisions:\n{clean_text}"
    )

    # Retry loop with a backoff delay for high-demand / rate-limit responses
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"   -> Gemini AI attempt {attempt} error: {e}")
            time.sleep(5 * attempt) # Wait longer with each failed attempt
        
    return "AI Summary temporarily unavailable due to high demand."

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
            
            # Generous delay to ensure free-tier token limits/burst limits aren't tripped
            time.sleep(4)

    if new_count > 0:
        existing.sort(key=lambda r: r.get("NEWS_DT") or "", reverse=True)
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(existing[:100], f, indent=2, ensure_ascii=False)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {new_count} new announcements.")

if __name__ == "__main__":
    run_once()
