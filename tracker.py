import os
import json
import requests

# -----------------------------
# Configuration & Keys
# -----------------------------
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
FRED_API_KEY = os.environ.get("FRED_API_KEY")

LEDGER_FILE = "ledger.json"

# Metrics from FRED (Public St. Louis Fed IDs)
# RRPONTSYD: Overnight Reverse Repo Facility (Billions)
# SOFR: Secured Overnight Financing Rate (%)
# WRESBAL: Reserve Balances with Federal Reserve Banks (Billions)
# WPC: Fed Discount Window Borrowings (Millions)
METRIC_REGISTRY = {
    "ON_RRP": {
        "fred_id": "RRPONTSYD",
        "name": "Overnight Reverse Repo (ON RRP)",
        "type": "dollar_balance", # uses 5% threshold
        "unit": "Billion"
    },
    "SOFR": {
        "fred_id": "SOFR",
        "name": "Secured Overnight Financing Rate",
        "type": "rate_bps",        # uses basis point threshold (>= 5 bps)
        "unit": "%"
    },
    "FED_RESERVES": {
        "fred_id": "WRESBAL",
        "name": "Fed Reserve Balances (H.4.1)",
        "type": "dollar_balance",
        "unit": "Billion"
    }
}

# -----------------------------
# Helpers
# -----------------------------
def load_ledger():
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE, "r") as f:
            return json.load(f)
    return {}

def save_ledger(data):
    with open(LEDGER_FILE, "w") as f:
        json.dump(data, f, indent=2)

def fetch_latest_fred_value(series_id):
    url = f"https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1
    }
    res = requests.get(url, params=params).json()
    observations = res.get("observations", [])
    if observations and observations[0]["value"] != ".":
        return float(observations[0]["value"]), observations[0]["date"]
    return None, None

def send_push_notification(title, message):
    url = "https://api.pushover.net/1/messages.json"
    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
        "priority": 0
    }
    requests.post(url, data=payload)

def generate_plain_english(metric_name, old_val, new_val, change_pct, change_diff, unit):
    """
    Translates raw metrics into practical layman language.
    """
    direction = "surged" if change_diff > 0 else "plummeted"
    
    if "Reverse Repo" in metric_name:
        if change_diff < 0:
            meaning = f"Financial institutions pulled ${abs(change_diff):.1f}B out of the Fed's cash-parking account and pushed it back into the financial system."
            impact = "Excess cash cushion is shrinking. If this continues, borrowing cash between banks could get tighter."
        else:
            meaning = f"Institutions parked an extra ${abs(change_diff):.1f}B at the Fed, choosing safe risk-free yield over lending to each other."
            impact = "Cash cushion expanded today; institutions are staying defensive."
            
    elif "Reserve Balances" in metric_name:
        if change_diff < 0:
            meaning = f"Total bank cash reserves held at the Fed fell by ${abs(change_diff):.1f}B."
            impact = "The overall liquidity cushion supporting commercial banks shrank this week."
        else:
            meaning = f"Bank reserves at the Fed increased by ${abs(change_diff):.1f}B."
            impact = "Commercial banks have a larger cash buffer to absorb financial shocks."
            
    elif "SOFR" in metric_name:
        bps_move = change_diff * 100
        meaning = f"The benchmark interest rate for overnight secured cash shifted by {abs(bps_move):.1f} basis points to {new_val:.2f}%."
        impact = "Borrowing cash against Treasury collateral became noticeably more expensive or cheaper."
    else:
        meaning = f"The indicator shifted by {change_pct:+.2f}% to {new_val} {unit}."
        impact = "Significant movement observed; monitoring continuation."

    body = (
        f"📊 The Move: {metric_name} {direction} by {abs(change_pct):.1f}% ({change_diff:+.2f} {unit}) to {new_val} {unit}.\n\n"
        f"💡 What It Means: {meaning}\n\n"
        f"🎯 Why It Matters: {impact}"
    )
    return body

# -----------------------------
# Main Execution Engine
# -----------------------------
def main():
    ledger = load_ledger()
    updated = False

    for key, meta in METRIC_REGISTRY.items():
        val, date_str = fetch_latest_fred_value(meta["fred_id"])
        if val is None:
            continue

        prev_entry = ledger.get(key)
        
        # First time seeing this metric: record baseline silently
        if not prev_entry:
            ledger[key] = {"value": val, "date": date_str}
            updated = True
            continue

        # If data hasn't updated on FRED yet, skip
        if prev_entry["date"] == date_str:
            continue

        old_val = prev_entry["value"]
        diff = val - old_val
        pct_change = (diff / old_val) * 100 if old_val != 0 else 0

        # Check threshold rules
        trigger_alert = False
        if meta["type"] == "dollar_balance" and abs(pct_change) >= 5.0:
            trigger_alert = True
        elif meta["type"] == "rate_bps" and abs(diff) >= 0.05: # 5 basis points
            trigger_alert = True

        if trigger_alert:
            title = f"🚨 MACRO ALERT: {meta['name']}"
            message = generate_plain_english(meta['name'], old_val, val, pct_change, diff, meta["unit"])
            send_push_notification(title, message)
            print(f"Alert sent for {key}: {pct_change:.2f}% shift.")

        # Update ledger with latest published date and value
        ledger[key] = {"value": val, "date": date_str}
        updated = True

    if updated:
        save_ledger(ledger)

if __name__ == "__main__":
    main()
