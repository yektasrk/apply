"""
config.py — Edit everything here before running python -m job_finder.main
"""

import os


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}

# ── Per-country config ──────────────────────────────────────────────────────────
# Each key is the country name you pass via --country
# Each value overrides: location, sheet tab, and optionally search terms
#
# Run:  python -m job_finder.main --country netherlands
#       python -m job_finder.main --country germany

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

# ── Runtime — set by job_finder.main from --country arg, don't edit ────────────
LOCATION:   str = ""
GOOGLE_SHEET_TAB: str = ""

# ── Scrape settings ─────────────────────────────────────────────────────────────
RESULTS_WANTED  = "50"
HOURS_OLD       = "720"   # jobs posted within N hours
REMOTE_ONLY     = False
JOB_TYPE        = "fulltime"        # fulltime | parttime | internship | contract | None
FETCH_DESCRIPTION = True

PROXIES: list[str] = [
    # "user:pass@1.2.3.4:8000",
]

# ── OpenAI compatibility matching ──────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
AI_MATCHING_REQUIRED = _env_flag("AI_MATCHING_REQUIRED", True)
RESUME_FILE = os.getenv("RESUME_FILE", "resume.md")
SUITABILITY_THRESHOLD = int(os.getenv("SUITABILITY_THRESHOLD", "50"))
MAX_JOB_DESCRIPTION_CHARS = int(os.getenv("MAX_JOB_DESCRIPTION_CHARS", "20000"))


GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "service_account.json",
)
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# ── Telegram ────────────────────────────────────────────────────────────────────
# 1. Message @BotFather on Telegram → /newbot → copy the token
# 2. Add the bot to your channel as an Administrator
# 3. For a public channel use "@your_channel_name"
#    For a private channel use the numeric ID e.g. "-1001234567890"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
