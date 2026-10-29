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

METRIC_REGISTRY = {
    "ON_RRP": {
        "fred_id": "RRPONTSYD",
        "name": "Overnight Reverse Repo (ON RRP)",
        "type": "pct",
        "threshold": 5.0,
        "unit": "Billion",
        "meaning_up": "Institutions parked more cash directly at the Fed, choosing zero-risk overnight yield over private market lending.",
        "meaning_down": "Institutions pulled cash out of the Fed parking facility and deployed it back into Treasury bills and commercial paper.",
        "impact": "This gauges remaining excess system liquidity. A persistent drain toward zero signals that surplus cash is evaporating and cash scarcity is approaching."
    },
    "SOFR": {
        "fred_id": "SOFR",
        "name": "Secured Overnight Financing Rate (SOFR)",
        "type": "bps",
        "threshold": 0.05, # 5 bps
        "unit": "%",
        "meaning_up": "The overnight cost for banks and institutions to borrow cash backed by Treasuries jumped.",
        "meaning_down": "The cost to borrow secured overnight cash eased, reflecting ample collateral funding.",
        "impact": "The core plumbing rate for the financial system. Spikes indicate that institutions are scrambling for cash or balance sheet room."
    },
    "FED_RESERVES": {
        "fred_id": "WRESBAL",
        "name": "Bank Reserve Balances at the Fed",
        "type": "pct",
        "threshold": 3.0,
        "unit": "Billion",
        "meaning_up": "Commercial bank cash balances deposited at the Fed increased.",
        "meaning_down": "Commercial bank reserves dropped, shrinking the primary liquidity buffer.",
        "impact": "Tracks whether the banking sector maintains 'abundant reserves'. Dropping reserves increase systemic vulnerability to credit shocks."
    },
    "DISCOUNT_WINDOW": {
        "fred_id": "WPC",
        "name": "Fed Discount Window (Emergency Borrowings)",
        "type": "diff",
        "threshold": 2000.0, # $2B spike
        "unit": "Million",
        "meaning_up": "Commercial banks tapped the Fed's emergency lender-of-last-resort facility for liquidity they couldn't secure privately.",
        "meaning_down": "Emergency liquidity borrowing subsided back toward baseline levels.",
        "impact": "Sudden spikes are the primary red flag for distress or panic at a commercial bank."
    },
    "CPI_INFLATION": {
        "fred_id": "CPIAUCSL",
        "name": "Consumer Price Index (Headline CPI)",
        "type": "pct",
        "threshold": 0.2,
        "unit": "Index",
        "meaning_up": "Consumer basket inflation accelerated faster than the prior monthly reading.",
        "meaning_down": "Consumer price growth cooled compared to the prior month.",
        "impact": "Constrains Fed policy. Hot inflation removes room to cut rates, while cooler prints support easing."
    },
    "FED_FUNDS": {
        "fred_id": "FEDFUNDS",
        "name": "Effective Federal Funds Rate",
        "type": "bps",
        "threshold": 0.15,
        "unit": "%",
        "meaning_up": "The Fed pushed benchmark interest rates higher, tightening overall financial conditions.",
        "meaning_down": "The Fed cut benchmark rates, easing borrowing costs across the economy.",
        "impact": "The ultimate steering wheel for yields, loans, mortgages, and private market debt."
    },
    "MORTGAGE_30Y": {
        "fred_id": "MORTGAGE30US",
        "name": "30-Year Fixed Mortgage Average",
        "type": "bps",
        "threshold": 0.10,
        "unit": "%",
        "meaning_up": "Home borrowing costs increased, adding pressure to monthly payment affordability.",
        "meaning_down": "Mortgage borrowing rates dipped, providing temporary relief for buyers and refinancers.",
        "impact": "Directly impacts housing transaction velocity, inventory lock-in, and residential valuations."
    },
    "CRUDE_OIL_WTI": {
        "fred_id": "DCOILWTICO",
        "name": "WTI Crude Oil Spot Price",
        "type": "pct",
        "threshold": 5.0,
        "unit": "$/bbl",
        "meaning_up": "Crude prices surged, driving fuel and transportation input costs higher across supply chains.",
        "meaning_down": "Crude prices sold off, alleviating energy and manufacturing input pressures.",
        "impact": "The primary upstream driver for headline inflation prints and central bank inflation expectations."
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

def main():
    ledger = load_ledger()
    updated = False

    for key, meta in METRIC_REGISTRY.items():
        val, date_str = fetch_latest_fred_value(meta["fred_id"])
        if val is None:
            continue

        prev_entry = ledger.get(key)

        if not prev_entry:
            ledger[key] = {"value": val, "date": date_str}
            updated = True
            print(f"Logged initial baseline for {key}: {val} on {date_str}")
            continue

        if prev_entry.get("date") == date_str:
            continue

        old_val = prev_entry["value"]
        diff = val - old_val
        pct_change = (diff / old_val) * 100 if old_val != 0 else 0

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
            print(f"Dispatched institutional alert for {key}!")

        ledger[key] = {"value": val, "date": date_str}
        updated = True

    if updated:
        save_ledger(ledger)

if __name__ == "__main__":
    main()
