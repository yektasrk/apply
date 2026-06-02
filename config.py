"""
config.py — Edit everything here before running main.py
"""

import os

# ── Per-country config ──────────────────────────────────────────────────────────
# Each key is the country name you pass via --country
# Each value overrides: location, sheet tab, and optionally search terms
#
# Run:  python main.py --country netherlands
#       python main.py --country germany

SEARCH_TERMS: list[str] = [
    '"Site Reliability Engineer"',
    '"Platform Engineer"',
    '"DevOps Engineer"',
    '"Infrastructure Engineer"',
]

COUNTRIES: dict[str, dict] = {
    "netherlands": {
        "location":   "Netherlands",
        "sheet_tab":  "Netherlands",
        "flag":       "🇳🇱",
    },
    "germany": {
        "location":   "Germany",
        "sheet_tab":  "Germany",
        "flag":       "🇩🇪",
    },
    "uk": {
        "location":   "United Kingdom",
        "sheet_tab":  "United Kingdom",
        "flag":       "🇬🇧",
    },
    "denmark": {
        "location":   "Denmark",
        "sheet_tab":  "Denmark",
        "flag":       "🇩🇰",
    },
    "ireland": {
        "location":   "Ireland",
        "sheet_tab":  "Ireland",
        "flag":       "🇮🇪",
    },
    "sweden": {
        "location":   "Sweden",
        "sheet_tab":  "Sweden",
        "flag":       "🇸🇪",
    },
    "switzerland": {
        "location":   "Switzerland",
        "sheet_tab":  "Switzerland",
        "flag":       "🇨🇭",
    },
    "portugal": {
        "location":   "Portugal",
        "sheet_tab":  "Portugal",
        "flag":       "🇵🇹",
    },
    "france": {
        "location":   "France",
        "sheet_tab":  "France",
        "flag":       "🇫🇷",
    },
}

# ── Runtime — set by main.py from --country arg, don't edit ────────────────────
LOCATION:   str = ""
GOOGLE_SHEET_TAB: str = ""

# ── Scrape settings ─────────────────────────────────────────────────────────────
RESULTS_WANTED    = int(os.getenv("RESULTS_WANTED", "50"))
HOURS_OLD         = int(os.getenv("HOURS_OLD",      "24"))
REMOTE_ONLY       = os.getenv("REMOTE_ONLY", "false").lower() == "true"
JOB_TYPE          = os.getenv("JOB_TYPE", "fulltime")
FETCH_DESCRIPTION = os.getenv("FETCH_DESCRIPTION", "true").lower() == "true"

PROXIES: list[str] = [
    # "user:pass@1.2.3.4:8000",
]

# ── Google Sheets ───────────────────────────────────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "LinkedIn Jobs")
GOOGLE_SHEET_ID   = os.getenv("GOOGLE_SHEET_ID",   "YOUR_SHEET_ID")

# ── Telegram ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN",  "YOUR_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@your_channel")
