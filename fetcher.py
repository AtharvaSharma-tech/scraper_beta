import io
import json
import os
import time
from datetime import date, datetime
import pdfplumber
import requests
import torch
from bse import BSE
from transformers import AutoModelForCausalLM, AutoTokenizer

DATA_FILE = "data/announcements.json"
ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

# 1. Load Qwen 2.5 (0.5B) locally (free, public, no sign-in required)
print("Loading Qwen 2.5 model...")
MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float32,
    low_cpu_mem_usage=True
)


def extract_pdf_text(attachment_name):
    """Download the BSE PDF and extract plain text."""
    if not attachment_name:
        return None
    url = ATTACHMENT_BASE_URL + attachment_name
    # User-agent header prevents BSE from blocking automated downloads
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            # Extract up to the first 4 pages
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:4])
        return text.strip()
    except Exception as e:
        print(f"Could not extract PDF text for {attachment_name}: {e}")
        return None


def summarize_text(company_name, category, text):
    """Summarize filing using Qwen without an API key."""
    if not text:
        return "No attachment content available."

    # Keep text to first 6,000 characters to process quickly on CPU
    content = text[:6000]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a financial analyst. Provide a 2-3 bullet point summary "
                "highlighting key financial numbers, board decisions, or material updates. "
                "Do not summarize letterheads or legal boilerplate."
            ),
        },
        {
            "role": "user",
            "content": f"Company: {company_name}\nCategory: {category}\n\nFiling Content:\n{content}"
        },
    ]

    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer([prompt], return_tensors="pt")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=140,
            do_sample=False,
            temperature=0.0
        )

    # Decode only the model's generated text
    generated_ids = [
        output_ids[len(input_ids):] 
        for input_ids, output_ids in zip(inputs.input_ids, outputs)
    ]
    summary = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    return summary.strip()


def load_existing():
    """Load previously saved announcements."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_announcements(announcements):
    """Save announcements to JSON."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(announcements, f, indent=2, ensure_ascii=False)


def fetch_latest():
    """Fetch today's announcements from BSE."""
    all_records = []
    today = date.today()

    with BSE(download_folder="./data") as bse:
        page_no = 1
        total_pages = 1

        while page_no <= total_pages:
            result = bse.announcements(page_no=page_no, from_date=today, to_date=today)
            records = result.get("Table", [])

            if not records:
                break

            all_records.extend(records)
            total_pages = records[0].get("TotalPageCnt", 1) or 1
            print(f"Fetched page {page_no}/{total_pages} ({len(records)} records)")
            page_no += 1
            time.sleep(1)

    return all_records


def run_once():
    existing = load_existing()
    existing_ids = {item.get("NEWSID") for item in existing}

    raw_records = fetch_latest()
    new_count = 0

    for raw in raw_records:
        record_id = raw.get("NEWSID")
        if record_id not in existing_ids:
            print(f"Summarizing filing for: {raw.get('SLONGNAME')}")
            pdf_text = extract_pdf_text(raw.get("ATTACHMENTNAME"))
            raw["summary"] = summarize_text(
                raw.get("SLONGNAME", "Company"),
                raw.get("NEWSSUB", "Filing"),
                pdf_text
            )
            # Store filing and mark seen
            existing.append(raw)
            existing_ids.add(record_id)
            new_count += 1
            time.sleep(0.5)

    if new_count > 0:
        # Keep latest 100 entries so file stays lightweight
        existing.sort(key=lambda r: r.get("NEWS_DT") or "", reverse=True)
        save_announcements(existing[:100])

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {new_count} new announcements.")


if __name__ == "__main__":
    # Runs a single batch execution and exits cleanly for GitHub Actions
    run_once()
