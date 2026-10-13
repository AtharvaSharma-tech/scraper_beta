import io
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
import pdfplumber
from curl_cffi import requests as cffi_requests
from summarizer import summarize

DATA_FILE = "data/announcements.json"
MAX_PER_RUN = 10
IST = timezone(timedelta(hours=5, minutes=30))

FINANCIAL_KEYWORDS = [
    "revenue", "income", "profit", "loss", "earnings", "sales", "turnover",
    "ebitda", "ebit", "assets", "liabilities", "equity", "capital", "debt",
    "cash", "expenses", "cost", "margin", "dividend", "eps", "share",
    "balance", "financial", "annual", "quarterly", "net", "gross",
    "operating", "total", "current", "non-current", "retained",
    "tax", "depreciation", "amortization", "interest", "borrowings",
    "investments", "receivables", "payables", "inventory", "fixed assets",
    "roce", "roe", "roa", "pe ratio", "book value", "face value",
    "crore", "lakh", "million", "billion", "₹", "inr", "rs", "rupee"
]


def now_ist():
    return datetime.now(IST)


def is_financial_table(table):
    """Check if a table likely contains financial data."""
    if not table or len(table) < 2:
        return False
    flat_text = " ".join(
        str(cell).lower()
        for row in table
        for cell in (row or [])
        if cell
    )
    return any(kw in flat_text for kw in FINANCIAL_KEYWORDS)


def clean_value(val):
    """Clean and normalize a cell value."""
    if val is None:
        return ""
    return str(val).strip().replace("\n", " ").replace("  ", " ")


def table_to_dict(table):
    """Convert a table (list of rows) to a list of dicts using header row."""
    if not table:
        return []
    rows = [[clean_value(c) for c in (row or [])] for row in table]
    header_idx = 0
    for i, row in enumerate(rows):
        if any(cell for cell in row):
            header_idx = i
            break
    headers = rows[header_idx]
    seen = {}
    clean_headers = []
    for h in headers:
        key = h if h else "col"
        if key in seen:
            seen[key] += 1
            key = f"{key}_{seen[key]}"
        else:
            seen[key] = 0
        clean_headers.append(key)

    data_rows = []
    for row in rows[header_idx + 1:]:
        if not any(cell for cell in row):
            continue
        padded = row + [""] * (len(clean_headers) - len(row))
        row_dict = {clean_headers[i]: padded[i] for i in range(len(clean_headers))}
        data_rows.append(row_dict)
    return data_rows


def extract_key_metrics_from_text(text):
    """Extract common financial figures mentioned in text using regex."""
    metrics = {}
    patterns = {
        "revenue":      r"(?:revenue|turnover|net sales)[^\d₹rs.]*[₹rs.]?\s*([\d,]+(?:\.\d+)?)\s*(?:crore|lakh|million|cr|mn)?",
        "net_profit":   r"(?:net profit|net income|pat)[^\d₹rs.]*[₹rs.]?\s*([\d,]+(?:\.\d+)?)\s*(?:crore|lakh|million|cr|mn)?",
        "total_assets": r"total assets[^\d₹rs.]*[₹rs.]?\s*([\d,]+(?:\.\d+)?)",
        "total_equity": r"(?:total equity|shareholders[' ]equity|networth|net worth)[^\d₹rs.]*[₹rs.]?\s*([\d,]+(?:\.\d+)?)",
        "eps":          r"\beps\b[^\d-]*(-?[\d,]+(?:\.\d+)?)",
        "face_value":   r"face value[^\d₹rs.]*[₹rs.]?\s*([\d,]+(?:\.\d+)?)",
        "book_value":   r"book value[^\d₹rs.]*[₹rs.]?\s*([\d,]+(?:\.\d+)?)",
        "dividend":     r"dividend[^\d₹rs.%]*[₹rs.]?\s*([\d,]+(?:\.\d+)?)\s*%?",
        "roce":         r"\broce\b[^\d%]*([0-9]+(?:\.[0-9]+)?)\s*%?",
        "roe":          r"\broe\b[^\d%]*([0-9]+(?:\.[0-9]+)?)\s*%?",
    }
    text_lower = text.lower()
    for key, pattern in patterns.items():
        match = re.search(pattern, text_lower)
        if match:
            metrics[key] = match.group(1).replace(",", "")
    return metrics


def extract_pdf_data(attachment_name):
    """
    Downloads the PDF once and extracts:
    - text for AI summary
    - financial_tables
    - key_metrics
    """
    if not attachment_name:
        return None, {}, []

    url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment_name}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    try:
        response = cffi_requests.get(url, headers=headers, impersonate="chrome", timeout=15)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text_for_summary = "\n".join(page.extract_text() or "" for page in pdf.pages[:3]).strip()

            financial_tables = []
            all_text_parts = []
            for page_num, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                all_text_parts.append(page_text)
                tables = page.extract_tables()
                for tbl_idx, table in enumerate(tables):
                    if is_financial_table(table):
                        tbl_data = table_to_dict(table)
                        if tbl_data:
                            financial_tables.append({
                                "page": page_num,
                                "table_index": tbl_idx,
                                "rows": tbl_data,
                            })
            full_text = "\n".join(all_text_parts)
            key_metrics = extract_key_metrics_from_text(full_text)

        return (text_for_summary if text_for_summary else None), key_metrics, financial_tables
    except Exception as e:
        print(f"   -> PDF extraction error: {e}")
        return None, {}, []


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
        pdf_text, key_metrics, financial_tables = extract_pdf_data(raw.get("ATTACHMENTNAME"))

        if pdf_text:
            summary = summarize(raw.get("SLONGNAME"), raw.get("NEWSSUB"), pdf_text)
            if not summary:
                summary = "* Summary unavailable (AI API key not configured or failed)."
        else:
            summary = "* Attachment contains no selectable text or is a scanned image."

        raw["summary"] = summary
        raw["key_metrics"] = key_metrics
        raw["financial_tables"] = financial_tables

        existing.append(raw)
        existing_ids.add(raw["NEWSID"])
        new_count += 1
        save(existing)  # incremental save so a crash doesn't lose progress
        time.sleep(2)

    print(f"Saved {new_count} new announcements.")


if __name__ == "__main__":
    print("fetcher.py started", flush=True)
    run_once()
