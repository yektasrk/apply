"""
scraper.py — LinkedIn scraping logic (shared by main.py and add_job.py)
"""

import logging

import pandas as pd
from jobspy import scrape_jobs
from tenacity import retry, retry_if_exception_type, RetryError

import config
from retries import RETRY

log = logging.getLogger(__name__)


@retry(**RETRY, retry=retry_if_exception_type(Exception))
def _scrape_one_term(term: str) -> pd.DataFrame:
    return scrape_jobs(
        site_name=["linkedin"],
        search_term=term,
        location=config.LOCATION,
        results_wanted=config.RESULTS_WANTED,
        hours_old=config.HOURS_OLD,
        is_remote=config.REMOTE_ONLY,
        job_type=config.JOB_TYPE,
        linkedin_fetch_description=config.FETCH_DESCRIPTION,
    )


@retry(**RETRY, retry=retry_if_exception_type(Exception))
def _scrape_by_id(job_id: str) -> pd.DataFrame:
    return scrape_jobs(
        site_name=["linkedin"],
        linkedin_job_ids=[job_id],
        linkedin_fetch_description=True,
    )


def scrape_all_terms() -> pd.DataFrame:
    """Scrape all SEARCH_TERMS from config and return a deduped DataFrame."""
    all_jobs: list[pd.DataFrame] = []

    for term in config.SEARCH_TERMS:
        log.info("Scraping LinkedIn for '%s' in '%s' …", term, config.LOCATION)
        try:
            jobs = _scrape_one_term(term)
            log.info("  → %d jobs found for '%s'.", len(jobs), term)
            if not jobs.empty:
                jobs["search_term"] = term
                all_jobs.append(jobs)
        except RetryError as e:
            log.error("  → All retries failed for '%s': %s", term, e)
        except Exception as e:
            log.error("  → Failed scraping '%s': %s", term, e)

    if not all_jobs:
        return pd.DataFrame()

    combined = pd.concat(all_jobs, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["job_url"], keep="first")
    dupes = before - len(combined)
    if dupes:
        log.info("Dropped %d cross-term duplicate(s).", dupes)

    log.info("Total unique jobs scraped: %d.", len(combined))
    return combined


def scrape_single_url(url: str) -> pd.Series:
    """Fetch a single job by its LinkedIn URL. Returns a Series."""
    job_id = _extract_job_id(url)
    log.info("Fetching job ID %s …", job_id)
    jobs = _scrape_by_id(job_id)
    if jobs.empty:
        raise RuntimeError(f"No job data returned for URL: {url}")
    return jobs.iloc[0]


def _extract_job_id(url: str) -> str:
    """Pull the numeric job ID out of a LinkedIn job URL."""
    parts = url.rstrip("/").split("/")
    for part in reversed(parts):
        clean = part.split("?")[0]
        if clean.isdigit():
            return clean
    raise ValueError(f"Could not extract job ID from URL: {url}")
