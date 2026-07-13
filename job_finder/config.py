"""
config.py — Edit everything here before running python -m job_finder.main
"""

import os


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


# ── Per-country config ──────────────────────────────────────────────────────────
# Each key is the country name you pass via --country
# Each value overrides: location, sheet tab, and optionally search terms
#
# Run:  python -m job_finder.main --country netherlands
#       python -m job_finder.main --country germany

SEARCH_TERMS: list[str] = _env_list(
    "SEARCH_TERMS",
    [
        '"Site Reliability Engineer"',
        '"Platform Engineer"',
        '"DevOps Engineer"',
        '"Infrastructure Engineer"',
    ],
)

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
RESULTS_WANTED = _env_int("RESULTS_WANTED", 50)
HOURS_OLD = _env_int("HOURS_OLD", 36)  # jobs posted within N hours
REMOTE_ONLY = _env_flag("REMOTE_ONLY", False)
JOB_TYPE = os.getenv("JOB_TYPE", "fulltime") or None
FETCH_DESCRIPTION = _env_flag("FETCH_DESCRIPTION", True)

# Jobs with any of these whole-word/phrase matches in the title are kept in
# the sheet for visibility, but pre-marked as unsuitable before manual triage.
TITLE_MISMATCH_KEYWORDS: tuple[str, ...] = (
    "AWS",
    "Azure",
    "Chief",
    "Staff",
    "Consultant",
    "Data Center",
    "MLOps",
    "Openstack",
    "OpenShift",
    "Windows",
    "Microsoft",
)
TITLE_MISMATCH_REASON = "title missmatch"

PROXIES: list[str] = _env_list("PROXIES", [])

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
