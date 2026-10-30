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

# =====================================================================
# MASTER MACRO & MONETARY PLUMBING REGISTRY
# =====================================================================
METRIC_REGISTRY = {
    # -------------------------------------------------------------
    # 1. DAILY MONETARY PLUMBING & INTERBANK STRESS
    # -------------------------------------------------------------
    "ON_RRP": {
        "fred_id": "RRPONTSYD",
        "name": "Overnight Reverse Repo Facility (ON RRP)",
        "type": "pct",
        "threshold": 5.0,
        "unit": "Billion",
        "meaning_up": "Cash parked at the Fed expanded. Institutions chose zero-risk central bank yield over private bills/paper.",
        "meaning_down": "Cash drained from the Fed's facility and flowed back into market instruments (T-bills, repo, deposits).",
        "impact": "Primary gauge of surplus system liquidity. Once drained near zero, interbank cash buffers are gone."
    },
    "SOFR": {
        "fred_id": "SOFR",
        "name": "Secured Overnight Financing Rate (SOFR)",
        "type": "bps",
        "threshold": 0.05, # 5 basis points
        "unit": "%",
        "meaning_up": "Secured interbank overnight borrowing rates spiked, indicating collateral or cash friction.",
        "meaning_down": "Cost of secured overnight lending eased across primary dealers.",
        "impact": "The bedrock rate of the plumbing. Jumps signal cash scarcity or balance sheet strain among primary dealers."
    },

    # -------------------------------------------------------------
    # 2. WEEKLY FED H.4.1 BALANCE SHEET (Thursdays 4:30 PM ET)
    # -------------------------------------------------------------
    "FED_ASSETS_TOTAL": {
        "fred_id": "WALCL",
        "name": "Fed Total Assets (Balance Sheet / QT)",
        "type": "pct",
        "threshold": 1.0,
        "unit": "Million",
        "meaning_up": "The Federal Reserve expanded its overall balance sheet assets (bond purchases or liquidity facilities).",
        "meaning_down": "The Fed's balance sheet contracted as bonds matured without reinvestment (Quantitative Tightening).",
        "impact": "Shows whether the central bank is actively draining liquidity from the financial system via QT."
    },
    "FED_RESERVES": {
        "fred_id": "WRESBAL",
        "name": "Commercial Bank Reserves at Fed (H.4.1)",
        "type": "pct",
        "threshold": 3.0,
        "unit": "Billion",
        "meaning_up": "Commercial bank cash deposits held at the Fed expanded.",
        "meaning_down": "Bank reserve deposits shrank, reducing the core cash buffer of the commercial banking system.",
        "impact": "Core liquidity gauge. Confirms if the banking system holds 'abundant reserves' or if stress is building."
    },
    "TGA_BALANCE": {
        "fred_id": "WTREGEN",
        "name": "Treasury General Account (TGA) Balance",
        "type": "pct",
        "threshold": 5.0,
        "unit": "Billion",
        "meaning_up": "The U.S. Treasury's checking account filled up, locking liquidity out of the commercial banking sector.",
        "meaning_down": "The Treasury spent money down into the economy, injecting cash directly into bank reserves.",
        "impact": "The TGA acts like a domestic liquidity sponge. Large fills tighten market cash; drawdowns provide a liquidity tailwind."
    },
    "DISCOUNT_WINDOW": {
        "fred_id": "WPC",
        "name": "Fed Discount Window Borrowings (Emergency Cash)",
        "type": "diff",
        "threshold": 2000.0, # Spike > $2 Billion (data reported in millions)
        "unit": "Million",
        "meaning_up": "Commercial banks tapped the Fed's emergency lender-of-last-resort facility for loans they couldn't get privately.",
        "meaning_down": "Emergency liquidity borrowing normalized back toward baseline levels.",
        "impact": "Definitive early-warning indicator for acute solvency or liquidity distress at commercial banks."
    },

    # -------------------------------------------------------------
    # 3. MACRO INFLATION & CENTRAL BANK POLICY
    # -------------------------------------------------------------
    "CPI_INFLATION": {
        "fred_id": "CPIAUCSL",
        "name": "Consumer Price Index (Headline CPI)",
        "type": "pct",
        "threshold": 0.2, # 0.2% monthly shift is significant
        "unit": "Index",
        "meaning_up": "Monthly consumer basket prices accelerated faster than the prior monthly reading.",
        "meaning_down": "Monthly consumer price inflation softened relative to the prior period.",
        "impact": "Defines real yield dynamics. Persistent inflation below official yields is the classic mechanism of financial repression."
    },
    "FED_FUNDS": {
        "fred_id": "FEDFUNDS",
        "name": "Effective Federal Funds Rate (FOMC Target)",
        "type": "bps",
        "threshold": 0.15,
        "unit": "%",
        "meaning_up": "The Fed pushed benchmark interest rates higher, tightening borrowing conditions.",
        "meaning_down": "The Fed cut benchmark rates, easing borrowing costs across the economy.",
        "impact": "The ultimate steering wheel for yields, loans, mortgages, and private equity financing."
    },

    # -------------------------------------------------------------
    # 4. REAL ESTATE & MORTGAGE DEBT
    # -------------------------------------------------------------
    "MORTGAGE_30Y": {
        "fred_id": "MORTGAGE30US",
        "name": "30-Year Fixed Mortgage Average",
        "type": "bps",
        "threshold": 0.10, # 10 bps
        "unit": "%",
        "meaning_up": "Home borrowing rates rose, making monthly debt service more expensive for buyers.",
        "meaning_down": "Home borrowing rates dipped, slightly improving debt service affordability.",
        "impact": "Directly impacts housing transaction velocity, inventory lock-in, and residential valuations."
    },

    # -------------------------------------------------------------
    # 5. COMMODITIES & UPSTREAM INFLATION
    # -------------------------------------------------------------
    "CRUDE_OIL_WTI": {
        "fred_id": "DCOILWTICO",
        "name": "WTI Crude Oil Spot Price",
        "type": "pct",
        "threshold": 5.0,
        "unit": "$/barrel",
        "meaning_up": "Crude oil prices surged by over 5%, pushing fuel input costs higher.",
        "meaning_down": "Crude oil tumbled over 5%, easing energy and manufacturing cost pressures.",
        "impact": "The primary upstream input cost for global supply chains and consumer headline inflation."
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
