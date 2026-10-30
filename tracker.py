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
# MASTER MACRO & MONETARY PLUMBING REGISTRY (10 CORE INDICATORS)
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
        "unit": "Million",
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
        "name":
