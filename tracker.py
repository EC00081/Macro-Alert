import os
import json
import requests

# -----------------------------
# Configuration & Secrets
# -----------------------------
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
FRED_API_KEY = os.environ.get("FRED_API_KEY")

LEDGER_FILE = "ledger.json"

# Complete registry of all your screenshot indicators
METRIC_REGISTRY = {
    # 1. Monetary Plumbing & Interbank Stress
    "ON_RRP": {
        "fred_id": "RRPONTSYD",
        "name": "Overnight Reverse Repo (ON RRP)",
        "type": "pct",
        "threshold": 5.0,
        "unit": "Billion",
        "meaning_up": "Institutions parked more cash at the Fed, choosing safe zero-risk yield over lending in the private market.",
        "meaning_down": "Institutions pulled cash out of the Fed parking spot and injected it back into Treasuries and short-term markets.",
        "impact": "Tracks remaining excess cash in the financial system. When this hits zero, cash becomes scarce."
    },
    "SOFR": {
        "fred_id": "SOFR",
        "name": "Secured Overnight Financing Rate (SOFR)",
        "type": "bps",
        "threshold": 0.05, # 5 bps
        "unit": "%",
        "meaning_up": "The overnight rate to borrow cash against Treasury collateral jumped.",
        "meaning_down": "The cost to borrow cash overnight against Treasury collateral decreased.",
        "impact": "The bedrock interest rate for the financial system. Spikes signal cash friction between banks."
    },

    # 2. Fed Balance Sheet & Bank Stress (H.4.1 Release)
    "FED_RESERVES": {
        "fred_id": "WRESBAL",
        "name": "Bank Reserve Balances at the Fed",
        "type": "pct",
        "threshold": 3.0,
        "unit": "Billion",
        "meaning_up": "Commercial bank reserves deposited at the Fed increased.",
        "meaning_down": "Commercial bank reserves at the Fed fell, shrinking the bank cash cushion.",
        "impact": "Shows whether the banking system holds 'abundant reserves' or if quantitative tightening is biting."
    },
    "DISCOUNT_WINDOW": {
        "fred_id": "WPC",
        "name": "Fed Discount Window Borrowings (Emergency Cash)",
        "type": "diff",
        "threshold": 2000.0, # Spike > $2 Billion (Units in millions)
        "unit": "Million",
        "meaning_up": "Banks tapped the Fed's emergency loan window for cash they couldn't get elsewhere.",
        "meaning_down": "Emergency borrowing from the Fed subsided back toward normal levels.",
        "impact": "A sudden spike is the primary early warning sign of distress at a commercial bank."
    },

    # 3. Macro Inflation & Central Bank Policy
    "CPI_INFLATION": {
        "fred_id": "CPIAUCSL",
        "name": "Consumer Price Index (Headline CPI)",
        "type": "pct",
        "threshold": 0.2, # 0.2% monthly move is significant
        "unit": "Index",
        "meaning_up": "Consumer basket prices accelerated faster than the prior month.",
        "meaning_down": "Consumer price growth cooled off compared to the prior month.",
        "impact": "Directly dictates whether the Fed has room to cut rates or must keep policy restrictive."
    },
    "FED_FUNDS": {
        "fred_id": "FEDFUNDS",
        "name": "Effective Federal Funds Rate (FOMC Target)",
        "type": "bps",
        "threshold": 0.15,
        "unit": "%",
        "meaning_up": "The Fed hiked benchmark interest rates, tightening borrowing conditions.",
        "meaning_down": "The Fed cut benchmark rates, easing financial conditions across the economy.",
        "impact": "The ultimate steering wheel for yields, loans, mortgages, and private equity financing."
    },

    # 4. Real Estate & Mortgage Debt
    "MORTGAGE_30Y": {
        "fred_id": "MORTGAGE30US",
        "name": "30-Year Fixed Mortgage Average",
        "type": "bps",
        "threshold": 0.10, # 10 bps
        "unit": "%",
        "meaning_up": "Home borrowing rates rose, making monthly mortgage payments more expensive.",
        "meaning_down": "Home borrowing rates dipped, slightly improving affordability for buyers.",
        "impact": "Drives housing market transaction volume, inventory lock-in, and coastal property pricing."
    },

    # 5. Energy Commodities
    "CRUDE_OIL_WTI": {
        "fred_id": "DCOILWTICO",
        "name": "WTI Crude Oil Spot Price",
        "type": "pct",
        "threshold": 5.0,
        "unit": "$/barrel",
        "meaning_up": "Crude oil prices surged by over 5%, pushing fuel input costs higher.",
        "meaning_down": "Crude oil tumbled over 5%, easing direct fuel and transport cost pressure.",
        "impact": "The primary upstream input cost for the supply chain and consumer headline inflation."
    }
}

# -----------------------------
# Core Pipeline Functions
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

def format_alert(meta, old_val, new_val, diff, pct_change):
    direction = "surged" if diff > 0 else "dropped"
    meaning = meta["meaning_up"] if diff > 0 else meta["meaning_down"]
    
    if meta["type"] == "bps":
        bps_move = abs(diff * 100)
        move_str = f"shifted by {bps_move:.1f} bps ({diff:+.2f}%) to {new_val:.2f}{meta['unit']}"
    elif meta["type"] == "diff":
        move_str = f"{direction} by {abs(diff):,.1f} {meta['unit']} to {new_val:,.1f} {meta['unit']}"
    else:
        move_str = f"{direction} by {abs(pct_change):.2f}% ({diff:+.2f} {meta['unit']}) to {new_val} {meta['unit']}"

    return (
        f"📊 The Move: {meta['name']} {move_str}.\n\n"
        f"💡 What It Means: {meaning}\n\n"
        f"🎯 Why It Matters: {meta['impact']}"
    )

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

        # If data hasn't refreshed on FRED yet, nothing new to report
        if prev_entry.get("date") == date_str:
            continue

        old_val = prev_entry["value"]
        diff = val - old_val
        pct_change = (diff / old_val) * 100 if old_val != 0 else 0

        # Threshold checking
        trigger = False
        if meta["type"] == "pct" and abs(pct_change) >= meta["threshold"]:
            trigger = True
        elif meta["type"] == "bps" and abs(diff) >= meta["threshold"]:
            trigger = True
        elif meta["type"] == "diff" and abs(diff) >= meta["threshold"]:
            trigger = True

        if trigger:
            title = f"🚨 MACRO ALERT: {meta['name']}"
            msg = format_alert(meta, old_val, val, diff, pct_change)
            send_push_notification(title, msg)
            print(f"Sent Pushover alert for {key}!")

        # Record latest observation in ledger
        ledger[key] = {"value": val, "date": date_str}
        updated = True

    if updated:
        save_ledger(ledger)

if __name__ == "__main__":
    main()
