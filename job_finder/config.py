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


def _sheet_setting(name: str, default: str = "") -> str:
    """Resolve a Google Sheets setting: env, then `config_local.py`, then default.

    CI is the real runtime for `job_finder.main` and passes these through the
    workflow env, so env keeps precedence and this cannot change what a scheduled
    scrape reads. `config_local.py` is git-ignored, so it simply does not exist
    there — the fallback is inert in CI by construction.

    Locally the opposite is true: there is no `.env`, and `config_local.py` is
    where the real spreadsheet ids live. Without this fallback every skill that
    wants the tracker has to re-implement the same lookup, which is exactly what
    `skills/report-job-market/scripts/pull.py` was forced to do.
    """
    value = os.getenv(name)
    if value:
        return value
    try:
        import config_local  # type: ignore
    except Exception:
        return default
    return getattr(config_local, name, None) or default


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

# job_status for roles found on a target company's own career page
# (job_finder.career_pages). It counts as Suitable everywhere — availability
# checks, applying, reporting — and triage leaves it alone.
ULTRA_SUITABLE_VALUE = "⭐ Ultra Suitable"

PROXIES: list[str] = _env_list("PROXIES", [])

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Anchored at the repo root rather than the CWD. CI writes service_account.json
# into the checkout root and runs from there, so this resolves to the same file
# it always did; what changes is that a script invoked from another directory
# (the skills under skills/*/scripts/) now finds it too.
GOOGLE_SERVICE_ACCOUNT_FILE = os.path.join(
    REPO_ROOT,
    _sheet_setting("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"),
)
GOOGLE_SHEET_NAME = _sheet_setting("GOOGLE_SHEET_NAME")
GOOGLE_SHEET_ID = _sheet_setting("GOOGLE_SHEET_ID")

# Spreadsheet that not-suitable rows are moved to before being deleted from the
# live sheet. Dedup reads it, so an unset value would silently re-import every
# archived job on the next scrape — job_finder.archive raises instead.
GOOGLE_ARCHIVE_SHEET_ID = _sheet_setting("GOOGLE_ARCHIVE_SHEET_ID")

# ── Telegram ────────────────────────────────────────────────────────────────────
# 1. Message @BotFather on Telegram → /newbot → copy the token
# 2. Add the bot to your channel as an Administrator
# 3. For a public channel use "@your_channel_name"
#    For a private channel use the numeric ID e.g. "-1001234567890"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
