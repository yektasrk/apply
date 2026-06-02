"""
main.py — Scrape LinkedIn jobs → Google Sheets + Telegram
Run: python main.py
"""

import asyncio
import argparse
import datetime
import logging

import config
import scraper
import sheets
import telegram_bot

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


def build_message(jobs, rows_written: int) -> str:
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🔍 *{rows_written} new jobs* — {now}", ""]

    for _, job in jobs.iterrows():
        title = job.get("title", "N/A")
        url   = job.get("job_url", "")
        flag  = telegram_bot.location_flag(str(job.get("location", "")))
        lines.append(f"{flag} [{title}]({url})" if url else f"{flag} {title}")

    lines.append(f"\n📊 [Open Sheet](https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID})")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True, help="Country key from config.COUNTRIES")
    args = parser.parse_args()
    configure_country(args.country)

    jobs = scraper.scrape_all_terms()

    if jobs.empty:
        log.warning("No jobs found. Exiting.")
        return

    rows_written, rows_skipped = sheets.push_jobs(jobs)
    log.info("Written: %d  |  Skipped (dupes): %d", rows_written, rows_skipped)

    await telegram_bot.send(build_message(jobs, rows_written))
    log.info("Done ✓")


if __name__ == "__main__":
    asyncio.run(main())
