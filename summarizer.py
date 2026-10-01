import os
import time
from curl_cffi import requests as http
from google import genai

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_MODEL = "gemini-3.8-flash"

_gemini_client = None


def _status(e):
    return getattr(e, "code", None) or getattr(getattr(e, "response", None), "status_code", None)


def _call_groq(prompt):
    r = http.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 300,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _call_gemini(prompt):
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = _gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (resp.text or "").strip()


def summarize(company, category, text):
    """Return a summary string, or None if every provider failed."""
    clean = text[:6000].replace("\n", " ").strip()
    prompt = (
        f"You are a financial analyst. Summarize this corporate announcement for {company} "
        f"({category}) in 2 clear bullet points focusing on key numbers, dates, or financial decisions. "
        f"Use only facts present in the text. If it has no financial details, say so.\n\n{clean}"
    )
    providers = []
    if os.environ.get("GROQ_API_KEY"):
        providers.append(("groq", _call_groq))
    if os.environ.get("GEMINI_API_KEY"):
        providers.append(("gemini", _call_gemini))

    if not providers:
        print("   -> No API keys set (GROQ_API_KEY / GEMINI_API_KEY).")
        return None

    for name, call in providers:
        for attempt in range(2):
            try:
                out = call(prompt)
                if out:
                    return out
                break
            except Exception as e:
                status = _status(e)
                print(f"   -> {name} attempt {attempt + 1} failed (status {status}): {e}")
                if status in (429, 500, 503) and attempt == 0:
                    time.sleep(10)  # retry only transient errors
                    continue
                break  # permanent error: move to next provider
    return None
