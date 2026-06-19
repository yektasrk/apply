"""
main.py — Scrape LinkedIn jobs → Google Sheets + Telegram
Run: python -m job_finder.main
"""

import asyncio
import argparse
import datetime
import logging
import sys

from . import config
from . import scraper
from . import sheets
from . import telegram_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def configure_country(country: str) -> None:
    try:
        country_config = config.COUNTRIES[country.lower()]
    except KeyError:
        available = ", ".join(sorted(config.COUNTRIES))
        raise SystemExit(f"Unknown country '{country}'. Available: {available}")

    config.LOCATION = country_config["location"]
    config.GOOGLE_SHEET_TAB = country_config["sheet_tab"]


def _job_message_entry(job, number: int) -> str:
    title = job.get("title", "N/A")
    url = job.get("job_url", "")
    company = job.get("company", "")
    location = job.get("location", "")
    flag = telegram_bot.location_flag(str(location))

    lines = [
        f"{number}. {flag} {telegram_bot.text_link(title, url)}",
    ]
    if company:
        lines.append(f"   Company: {telegram_bot.escape(company)}")
    if location:
        lines.append(f"   Location: {telegram_bot.escape(location)}")
    return "\n".join(lines)


def _message_page(entries: list[str], rows_written: int, page: int, total_pages: int) -> str:
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    country = telegram_bot.escape(config.LOCATION)
    flag = telegram_bot.location_flag(config.LOCATION)
    page_label = f" ({page}/{total_pages})" if total_pages > 1 else ""
    sheet_url = f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}"

    return "\n".join(
        [
            f"<b>{flag} {country}</b>{page_label}",
            f"<b>{rows_written} new jobs</b> — {now}",
            "",
            f"<blockquote expandable>{chr(10).join(entries)}</blockquote>",
            "",
            f"📊 {telegram_bot.text_link('Open Sheet', sheet_url)}",
        ]
    )


def build_messages(jobs, rows_written: int) -> list[str]:
    if rows_written == 0 or jobs.empty:
        return []

    entries = [
        _job_message_entry(job, number)
        for number, (_, job) in enumerate(jobs.iterrows(), start=1)
    ]
    pages: list[list[str]] = []
    current: list[str] = []

    for entry in entries:
        candidate = current + [entry]
        preview = _message_page(candidate, rows_written, 999, 999)
        if current and len(preview) > telegram_bot.MESSAGE_LIMIT:
            pages.append(current)
            current = [entry]
        else:
            current = candidate
    if current:
        pages.append(current)

    total_pages = len(pages)
    return [
        _message_page(page_entries, rows_written, page, total_pages)
        for page, page_entries in enumerate(pages, start=1)
    ]


def validate_configs() -> None:
    missing = []
    if config.GOOGLE_SHEET_ID in ("", "YOUR_SHEET_ID"):
        missing.append("GOOGLE_SHEET_ID")
    if config.TELEGRAM_BOT_TOKEN in ("", "YOUR_BOT_TOKEN"):
        missing.append("TELEGRAM_BOT_TOKEN")
    if config.TELEGRAM_CHANNEL_ID in ("", "@your_channel"):
        missing.append("TELEGRAM_CHANNEL_ID")
    if missing:
        print(f"❌ Missing or unconfigured secrets: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True, help="Country key from config.COUNTRIES")
    args = parser.parse_args()
    configure_country(args.country)
    validate_configs()

    jobs = scraper.scrape_all_terms()

    if jobs.empty:
        log.warning("No jobs found. Exiting.")
        return

    rows_written, rows_skipped, new_jobs = sheets.push_jobs(jobs)
    log.info("Written: %d  |  Skipped (dupes): %d", rows_written, rows_skipped)

    messages = build_messages(new_jobs, rows_written)
    if messages:
        await telegram_bot.send(messages)
    log.info("Done ✓")


if __name__ == "__main__":
    asyncio.run(main())
