# 📈 BSE Announcement Summariser & Financial Data Extractor

An automated pipeline that monitors live Bombay Stock Exchange (BSE) corporate announcements, downloads PDF filings, extracts financial metrics and tables, synthesizes bullet-point summaries using AI, and publishes them to a responsive web dashboard.

---

## 🚀 Features

- **Live BSE Scraping**: Connects to the BSE Corporate Announcements API during trading hours to track real-time filings.
- **AI-Powered Summarization**: Summarizes complex regulatory filings into concise, high-impact bullet points focusing on dates, values, and key corporate actions (via Groq or Google Gemini).
- **Financial Table Extraction**:
  - Automatically parses PDF tables using `pdfplumber`.
  - Built-in validation filters out non-tabular content (cover letters, recipient addresses, and letterheads).
  - Retains genuine financial tables (balance sheets, profit & loss, voting outcomes).
- **Key Metrics Extraction**:
  - Extracts metrics including **Revenue**, **Net Profit (PAT)**, **EBITDA / Operating Profit**, **Total Assets**, **Total Equity**, **Total Debt**, **EPS**, **Dividend**, **ROCE**, **ROE**, and **Currency Units** (`₹ in Crores`, `₹ in Lakhs`, etc.).
- **Interactive Web Interface**:
  - Clean dark-mode dashboard built with vanilla HTML/CSS and JavaScript.
  - Collapsible tables and metric badges for every filing.
  - One-click link to view the official original BSE PDF attachment.
- **Automated CI/CD**:
  - Runs every 30 minutes (Monday to Friday) via GitHub Actions.
  - Automatically deploys the updated dashboard to GitHub Pages.

---

## 📁 Project Structure

```text
scraper_beta/
├── .github/
│   └── workflows/
│       └── scrape.yml         # GitHub Actions schedule (every 30 mins) & deployment
├── data/
│   └── announcements.json     # Rolling storage of the latest 100 announcements & metrics
├── .gitignore
├── fetcher.py                 # Core scraping, PDF downloading & financial extraction engine
├── index.html                 # Frontend dashboard displaying announcements & financial data
├── requirements.txt           # Python dependencies
├── summarizer.py              # AI summarization module (Groq / Gemini)
└── README.md
```

---

## 🛠️ Local Setup & Usage

### 1. Prerequisites
- Python 3.10+
- (Optional) API Keys: `GROQ_API_KEY` and/or `GEMINI_API_KEY` (if generating AI summaries locally)

### 2. Installation

Clone the repository and set up a virtual environment:

```bash
git clone https://github.com/AtharvaSharma-tech/scraper_beta.git
cd scraper_beta

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Scraper Locally

```bash
# Set your AI API key (optional, scraper runs financial extraction even without it)
export GEMINI_API_KEY="your-gemini-key"
# or
export GROQ_API_KEY="your-groq-key"

# Run the fetcher
python fetcher.py
```

`fetcher.py` will:
1. Poll the BSE API for today's unprocessed filings.
2. Download PDFs and extract text, financial tables, and key metrics.
3. Generate AI summaries (if API keys are present).
4. Save the top 100 latest filings into `data/announcements.json`.

### 4. Run the Web Dashboard Locally

Start a simple HTTP server:

```bash
python3 -m http.server 8000
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## ⚙️ Configuration & Scheduling

The automated pipeline is scheduled in [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml):
- **Cron Schedule:** `*/30 * * * 1-5` (every 30 minutes from Monday to Friday).
- **Manual Execution:** Triggerable manually under the **Actions** tab on GitHub via `workflow_dispatch`.
- **Secrets Required:**
  - `GEMINI_API_KEY`
  - `GROQ_API_KEY`

---

## 📄 License

MIT License. Feel free to use and adapt this project for research or personal use.