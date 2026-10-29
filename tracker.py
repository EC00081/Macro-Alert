import os
import json
import requests

# -----------------------------
# Configuration & Credentials
# -----------------------------
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
FRED_API_KEY = os.environ.get("FRED_API_KEY")

LEDGER_FILE = "ledger.json"

# Core Monetary Plumbing & Liquidity Indicators
METRIC_REGISTRY = {
    # 1. Overnight Reverse Repo (ON RRP)
    "ON_RRP": {
        "fred_id": "RRPONTSYD",
        "name": "Overnight Reverse Repo Facility",
        "type": "pct",
        "threshold": 5.0,
        "unit": "Billion",
        "meaning_up": "Cash parked at the Fed expanded. Money funds and dealers chose zero-risk central bank yield over private bills/paper.",
        "meaning_down": "Cash drained from the Fed's facility and flowed back into market instruments (T-bills, repo, deposits).",
        "impact": "Primary gauge of surplus system liquidity. Once drained near zero, interbank cash buffers are effectively gone."
    },

    # 2. Benchmark Secured Overnight Financing Rate (SOFR)
    "SOFR": {
        "fred_id": "SOFR",
        "name": "SOFR Benchmark Rate",
        "type": "bps",
        "threshold": 0.05, # 5 basis points
        "unit": "%",
        "meaning_up": "Secured interbank overnight borrowing rates spiked, indicating collateral or cash friction.",
        "meaning_down": "Cost of secured overnight lending eased across primary dealers.",
        "impact": "The bedrock rate of the plumbing. Jumps signal cash scarcity or balance sheet strain among primary dealers."
    },

    # 3. Commercial Bank Reserves at the Fed (H.4.1)
    "FED_RESERVES": {
        "fred_id": "WRESBAL",
        "name": "Commercial Bank Reserves at Fed",
        "type": "pct",
        "threshold": 3.0,
        "unit": "Billion",
        "meaning_up": "Total reserves deposited by banks at the central bank expanded.",
        "meaning_down": "Bank reserve balances shrank, drawing down the system's baseline liquidity cushion.",
        "impact": "Shows whether the banking system remains in 'abundant reserves' territory or is drifting toward stress."
    },

    # 4. Emergency Discount Window (Primary Credit)
    "DISCOUNT_WINDOW": {
        "fred_id": "WPC",
        "name": "Fed Discount Window Borrowings",
        "type": "diff",
        "threshold": 2000.0, # $2B jump (data in millions)
        "unit": "Million",
        "meaning_up": "Commercial banks tapped emergency lender-of-last-resort funds, unable to source liquidity in private markets.",
        "meaning_down": "Emergency borrowing normalized back toward baseline levels.",
        "impact": "The definitive early-warning signal for acute solvency or liquidity distress at depository institutions."
    },

    # 5. Headline Consumer Price Index (CPI)
    "CPI_INFLATION": {
        "fred_id": "CPIAUCSL",
        "name": "Consumer Price Index (CPI)",
        "type": "pct",
        "threshold": 0.2,
        "unit": "Index",
        "meaning_up": "Monthly inflation pressure accelerated, reinforcing sticky price dynamics.",
        "meaning_down": "Monthly consumer price inflation softened relative to the prior period.",
        "impact": "Defines real yield dynamics. Persistent inflation below official yields is the classic mechanism of financial repression."
    },

    # 6. Effective Federal Funds Rate (EFFR)
    "FED_FUNDS": {
        "fred_id": "FEDFUNDS",
        "name": "Effective Federal Funds Rate",
        "type": "bps",
        "threshold": 0.15,
        "unit": "%",
        "meaning_up": "Fed executed a policy rate increase, tightening broad monetary conditions.",
        "meaning_down": "Fed executed a rate cut, easing policy rates across credit markets.",
        "impact": "Anchor rate for public debt refinancing costs and private credit benchmarks."
    },

    # 7. 30-Year Fixed Mortgage Average
    "MORTGAGE_30Y": {
        "fred_id": "MORTGAGE30US",
        "name": "30-Year Fixed Mortgage Rate",
        "type": "bps",
        "threshold": 0.10, # 10 bps
        "unit": "%",
        "meaning_up": "Mortgage financing costs climbed, increasing debt-service friction for real estate buyers.",
        "meaning_down": "Mortgage financing rates dipped, marginally reducing borrower cost of capital.",
        "impact": "Dictates residential credit creation, liquidity lock-in, and housing transaction velocity."
    },

    # 8. WTI Spot Crude Oil
    "CRUDE_OIL_WTI": {
        "fred_id": "DCOILWTICO",
        "name": "WTI Crude Oil Spot",
        "type": "pct",
        "threshold": 5.0,
        "unit": "$/bbl",
        "meaning_up": "Crude oil spiked, injecting cost-push energy inflation into headline metrics.",
        "meaning_down": "Crude prices retreated, reducing upstream transportation and manufacturing input costs.",
        "impact": "Core input cost for industrial activity and sovereign inflation calculations."
    }
}

# -----------------------------
# Storage & Data Retrieval
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
        print(f"Pushover dispatch failed: {e}")

def build_analyst_brief(meta, old_val, new_val, diff, pct_change):
    direction = "jumped" if diff > 0 else "dropped"
    meaning = meta["meaning_up"] if diff > 0 else meta["meaning_down"]

    if meta["type"] == "bps":
        bps_move = abs(diff * 100)
        move_line = f"{meta['name']} {direction} by {bps_move:.1f} bps ({diff:+.2f}%) to {new_val:.2f}{meta['unit']}."
    elif meta["type"] == "diff":
        move_line = f"{meta['name']} {direction} by {abs(diff):,.1f} {meta['unit']} to {new_val:,.1f} {meta['unit']}."
    else:
        move_line = f"{meta['name']} {direction} by {abs(pct_change):.2f}% ({diff:+.2f} {meta['unit']}) to {new_val:,.2f} {meta['unit']}."

    return (
        f"The Move: {move_line}\n\n"
        f"What It Means: {meaning}\n\n"
        f"Why It Matters: {meta['impact']}"
    )

# -----------------------------
# Execution Loop
# -----------------------------
def main():
    ledger = load_ledger()
    updated = False

    for key, meta in METRIC_REGISTRY.items():
        val, date_str = fetch_latest_fred_value(meta["fred_id"])
        if val is None:
            continue

        prev_entry = ledger.get(key)

        # Baseline capture on initial run
        if not prev_entry:
            ledger[key] = {"value": val, "date": date_str}
            updated = True
            print(f"Recorded baseline for {key}: {val} on {date_str}")
            continue

        # If data date hasn't shifted, skip
        if prev_entry.get("date") == date_str:
            continue

        old_val = prev_entry["value"]
        diff = val - old_val
        pct_change = (diff / old_val) * 100 if old_val != 0 else 0

        # Deterministic Threshold Gate
        trigger = False
        if meta["type"] == "pct" and abs(pct_change) >= meta["threshold"]:
            trigger = True
        elif meta["type"] == "bps" and abs(diff) >= meta["threshold"]:
            trigger = True
        elif meta["type"] == "diff" and abs(diff) >= meta["threshold"]:
            trigger = True

        if trigger:
            title = f"🚨 MACRO ALERT: {meta['name']}"
            body = build_analyst_brief(meta, old_val, val, diff, pct_change)
            send_push_notification(title, body)
            print(f"Trigger tripped for {key}! Sent notification.")

        # Update ledger with latest date and figure
        ledger[key] = {"value": val, "date": date_str}
        updated = True

    if updated:
        save_ledger(ledger)

if __name__ == "__main__":
    main()
