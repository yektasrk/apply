"""
add_job.py — Manually add a single LinkedIn job URL to the Google Sheet
Usage: python add_job.py https://www.linkedin.com/jobs/view/1234567890
"""

import argparse
import logging

import config
import scraper
import sheets

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="LinkedIn job URL")
    parser.add_argument("--country", required=True, help="Country key from config.COUNTRIES")
    args = parser.parse_args()

    configure_country(args.country)
    url = args.url.strip()

    job = scraper.scrape_single_url(url)
    log.info("Fetched: '%s' @ %s", job.get("title"), job.get("company"))

    written = sheets.push_single(job)

    if written:
        print(f"\n✅ Added: {job.get('title')} @ {job.get('company')} ({job.get('location')})")
    else:
        print(f"\n⚠️  Already in sheet: {job.get('title')} @ {job.get('company')}")


if __name__ == "__main__":
    main()
