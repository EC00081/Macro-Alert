import os
import json
import requests

# -----------------------------
# Configuration & Secrets
# -----------------------------
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
FRED_API_KEY = os.environ.get("FRED_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

LEDGER_FILE = "ledger.json"

METRIC_REGISTRY = {
    "ON_RRP": {
        "fred_id": "RRPONTSYD",
        "name": "Overnight Reverse Repo (ON RRP)",
        "type": "pct",
        "threshold": 5.0,
        "unit": "Billion"
    },
    "SOFR": {
        "fred_id": "SOFR",
        "name": "Secured Overnight Financing Rate (SOFR)",
        "type": "bps",
        "threshold": 0.05,
        "unit": "%"
    },
    "FED_RESERVES": {
        "fred_id": "WRESBAL",
        "name": "Bank Reserve Balances at the Fed",
        "type": "pct",
        "threshold": 3.0,
        "unit": "Billion"
    },
    "DISCOUNT_WINDOW": {
        "fred_id": "WPC",
        "name": "Fed Discount Window Borrowings (Emergency Cash)",
        "type": "diff",
        "threshold": 2000.0,
        "unit": "Million"
    },
    "CPI_INFLATION": {
        "fred_id": "CPIAUCSL",
        "name": "Consumer Price Index (Headline CPI)",
        "type": "pct",
        "threshold": 0.2,
        "unit": "Index"
    },
    "FED_FUNDS": {
        "fred_id": "FEDFUNDS",
        "name": "Effective Federal Funds Rate (FOMC Target)",
        "type": "bps",
        "threshold": 0.15,
        "unit": "%"
    },
    "MORTGAGE_30Y": {
        "fred_id": "MORTGAGE30US",
        "name": "30-Year Fixed Mortgage Average",
        "type": "bps",
        "threshold": 0.10,
        "unit": "%"
    },
    "CRUDE_OIL_WTI": {
        "fred_id": "DCOILWTICO",
        "name": "WTI Crude Oil Spot Price",
        "type": "pct",
        "threshold": 5.0,
        "unit": "$/barrel"
    }
}

# -----------------------------
# Pipeline Helpers
# -----------------------------
def load_ledger():
    if os.path.exists(LEDGER_FILE):
        try:
            with open(LEDGER_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_ledger(data):
    with open(LEDGER_FILE, "w") as f:
        json.dump(data, f, indent=2)

def fetch_latest_fred_value(series_id):
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1
    }
    try:
        res = requests.get(url, params=params, timeout=10).json()
        observations = res.get("observations", [])
        if observations and observations[0]["value"] != ".":
            return float(observations[0]["value"]), observations[0]["date"]
    except Exception as e:
        print(f"Error fetching {series_id}: {e}")
    return None, None

def ask_gemini_translator(metric_name, old_val, new_val, diff, pct_change, unit):
    """
    Hands off raw numbers to Gemini to write concise plain-English market briefs.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
You are a plain-English macro financial analyst for an investor.
Translate this official data move into simple, everyday language without corporate jargon:

Indicator: {metric_name}
Previous Reading: {old_val} {unit}
New Reading: {new_val} {unit}
Absolute Change: {diff:+.2f} {unit}
Percentage Change: {pct_change:+.2f}%

Format your response strictly as follows (no asterisks, keep it short and punchy for a mobile screen):
The Move: [1 concise sentence stating the change in numbers and direction]
What It Means: [1-2 sentences explaining what physically happened to the money/market in simple layman terms]
Why It Matters: [1-2 sentences on what this practically signals for interest rates, banks, or the broader market]
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        res_data = response.json()
        generated_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return generated_text
    except Exception as e:
        print(f"Gemini API fallback error: {e}")
        # Fallback if the API fails or rate-limits
        return (
            f"The Move: {metric_name} shifted by {pct_change:+.2f}% ({diff:+.2f} {unit}) to {new_val} {unit}.\n\n"
            f"What It Means: Significant change detected crossing your threshold.\n\n"
            f"Why It Matters: Review official report for market impact."
        )

def send_push_notification(title, message):
    url = "https://api.pushover.net/1/messages.json"
    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
        "priority": 0
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Failed to dispatch Pushover alert: {e}")

def main():
    ledger = load_ledger()
    updated = False

    for key, meta in METRIC_REGISTRY.items():
        val, date_str = fetch_latest_fred_value(meta["fred_id"])
        if val is None:
            continue

        prev_entry = ledger.get(key)

        # Baseline capture on first discovery
        if not prev_entry:
            ledger[key] = {"value": val, "date": date_str}
            updated = True
            print(f"Logged initial baseline for {key}: {val} on {date_str}")
            continue

        # If FRED hasn't updated the date yet, skip
        if prev_entry.get("date") == date_str:
            continue

        old_val = prev_entry["value"]
        diff = val - old_val
        pct_change = (diff / old_val) * 100 if old_val != 0 else 0

        # Check thresholds
        trigger = False
        if meta["type"] == "pct" and abs(pct_change) >= meta["threshold"]:
            trigger = True
        elif meta["type"] == "bps" and abs(diff) >= meta["threshold"]:
            trigger = True
        elif meta["type"] == "diff" and abs(diff) >= meta["threshold"]:
            trigger = True

        if trigger:
            title = f"🚨 MACRO ALERT: {meta['name']}"
            print(f"Threshold triggered for {key}! Asking Gemini to summarize...")
            plain_english_body = ask_gemini_translator(meta["name"], old_val, val, diff, pct_change, meta["unit"])
            send_push_notification(title, plain_english_body)
            print(f"Sent Pushover alert for {key}!")

        ledger[key] = {"value": val, "date": date_str}
        updated = True

    if updated:
        save_ledger(ledger)

if __name__ == "__main__":
    main()
