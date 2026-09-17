"""
career_pages.py — Read target companies' own career pages → Google Sheets + Telegram

Run: python -m job_finder.career_pages --country netherlands [--dry-run] [--company NAME]

Each company in `company_boards.BOARDS` is read from the source its careers page
itself uses: the public job-board feed behind it (Greenhouse, Lever, ...) when
there is one, or the page's own HTML when the company hosts its jobs itself.
LinkedIn is never consulted. Matching roles — right title family, located in the
Netherlands — are appended to the country tab with the same dedup as the
LinkedIn scrape, plus a company+title check so a role already imported from
LinkedIn under a different URL is not added twice.
"""

import argparse
import asyncio
import datetime
import html
import json
import logging
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable

import pandas as pd
from tenacity import retry, retry_if_exception

from . import config
from . import main as scrape_main
from . import scraper
from . import sheets
from . import telegram_bot
from .check_availability import HTTPS_CONTEXT
from .company_boards import BOARDS, Board
from .retries import RETRY

log = logging.getLogger(__name__)

SOURCE_LABEL = "Career pages"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
TIMEOUT_SECONDS = 20
MAX_DESCRIPTION_CHARS = 45_000  # Google Sheets rejects cells over 50,000 chars.
MAX_DETAIL_FETCHES = 40  # per board, for sources that need one request per job
FAILURE_RATIO_LIMIT = 0.30
WORKERS = 8

TITLE_INCLUDE_KEYWORDS: tuple[str, ...] = (
    "Site Reliability",
    "SRE",
    "Reliability Engineer",
    "Reliability Engineering",
    "Platform Engineer",
    "Platform Engineering",
    "Developer Platform",
    "DevOps",
    "Dev Ops",
    "DevSecOps",
    "Infrastructure",
    "Cloud Engineer",
    "Cloud Native",
    "Cloud Operations",
    "Cloud Platform",
    "Operations Engineer",
    "Production Engineer",
    "Systems Engineer",
    "System Engineer",
    "Systems Software Engineer",
    "System Administrator",
    "Systems Administrator",
    "Linux",
    "Kubernetes",
    "Observability",
    "Storage Engineer",
    "Network Engineer",
    "Network Automation",
    "HPC",
)
TITLE_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "Intern",
    "Internship",
    "Junior",
    "Graduate",
    "Trainee",
    "Early Talent",
    "Early Career",
    "New Grad",
    "Student",
    "Working Student",
    "Werkstudent",
    "Stage",
    "Stagiair",
    "Manager",
    "Director",
    "Head of",
    "VP",
    "Sales",
    "Assistant",
    "Writer",
)
TITLE_INCLUDE_PATTERN = scraper._build_title_pattern(TITLE_INCLUDE_KEYWORDS)
TITLE_EXCLUDE_PATTERN = scraper._build_title_pattern(TITLE_EXCLUDE_KEYWORDS)

NETHERLANDS_PATTERN = scraper._build_title_pattern(
    (
        "Netherlands",
        "Nederland",
        "Holland",
        "Amsterdam",
        "Rotterdam",
        "Utrecht",
        "Eindhoven",
        "The Hague",
        "Den Haag",
        "'s-Gravenhage",
        "Delft",
        "Leiden",
        "Almere",
        "Enschede",
        "Hilversum",
        "Breda",
        "Diemen",
        "Amstelveen",
        "Schiphol",
        "Hoofddorp",
        "Nijmegen",
        "Arnhem",
        "Groningen",
        "Haarlem",
        "Zwolle",
        "Amersfoort",
        "Den Bosch",
        "'s-Hertogenbosch",
        "Nieuwegein",
        "Veenendaal",
        "Apeldoorn",
    )
)
# Uppercase country codes only: a case-insensitive "nl" matches too much.
NETHERLANDS_CODE_PATTERN = re.compile(r"(?<![A-Za-z])(?:NL|NLD)(?![A-Za-z])")
REMOTE_PATTERN = re.compile(r"\bremote\b", re.IGNORECASE)
REMOTE_REGION_PATTERN = re.compile(r"\b(?:europe|european|emea|eu)\b", re.IGNORECASE)

JOB_FIELDS = ("title", "company", "location", "job_url", "date_posted", "description", "is_remote")


# ── Filters ─────────────────────────────────────────────────────────────────────


def title_matches(title: str) -> bool:
    """True for a title in the user's role family that is not junior or managerial."""
    text = str(title or "")
    return bool(TITLE_INCLUDE_PATTERN.search(text)) and not TITLE_EXCLUDE_PATTERN.search(text)


def location_matches(location: str, is_remote: bool = False) -> bool:
    """True for a Netherlands location, or a remote role open across Europe."""
    text = str(location or "")
    if NETHERLANDS_PATTERN.search(text) or NETHERLANDS_CODE_PATTERN.search(text):
        return True
    remote = is_remote or bool(REMOTE_PATTERN.search(text))
    return remote and bool(REMOTE_REGION_PATTERN.search(text))


# ── Text helpers ────────────────────────────────────────────────────────────────


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}
    SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    """Plain text from an HTML fragment, one block per line, capped for Sheets."""
    parser = _TextExtractor()
    parser.feed(str(markup or ""))
    parser.close()
    text = "".join(parser.parts)
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines()]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return cleaned[:MAX_DESCRIPTION_CHARS]


def iso_date(value: object) -> str:
    """YYYY-MM-DD from an ISO string, a date-time string, or epoch milliseconds."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value / 1000, datetime.UTC).strftime("%Y-%m-%d")
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value).strip())
    return match.group(1) if match else ""


def _job(**fields) -> dict:
    job = {name: fields.get(name, "") for name in JOB_FIELDS}
    job["is_remote"] = bool(fields.get("is_remote", False))
    job["title"] = re.sub(r"\s+", " ", str(job["title"])).strip()
    return job


# ── HTTP ────────────────────────────────────────────────────────────────────────


class HttpError(Exception):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, HttpError):
        return exc.status == 429 or exc.status >= 500
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, ssl.SSLCertVerificationError):
        return False  # a certificate problem fails identically on every attempt
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError))


@retry(**RETRY, retry=retry_if_exception(_is_retryable))
def http_get(
    url: str,
    body: dict | None = None,
    accept: str = "application/json",
    extra_headers: dict | None = None,
) -> bytes:
    """GET (or POST a JSON body) and return the response bytes."""
    headers = {"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"}
    headers.update(extra_headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=HTTPS_CONTEXT) as response:
            return response.read(100_000_000)
    except urllib.error.HTTPError as exc:
        raise HttpError(exc.code, url) from exc


def http_json(url: str, body: dict | None = None):
    return json.loads(http_get(url, body))


# ── Parsers (pure) and fetchers (HTTP + parser) ─────────────────────────────────

Fetcher = Callable[[Board], list[dict]]


def parse_greenhouse(payload: dict, company: str) -> list[dict]:
    jobs = []
    for item in payload.get("jobs", []):
        offices = [o.get("location") or o.get("name") or "" for o in item.get("offices") or []]
        location = "; ".join(
            dict.fromkeys(
                part for part in [(item.get("location") or {}).get("name", ""), *offices] if part
            )
        )
        jobs.append(
            _job(
                title=item.get("title", ""),
                company=company,
                location=location,
                job_url=item.get("absolute_url", ""),
                date_posted=iso_date(item.get("first_published") or item.get("updated_at")),
                description=html_to_text(html.unescape(item.get("content") or "")),
            )
        )
    return jobs


def fetch_greenhouse(board: Board) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board.slug}/jobs?content=true"
    return parse_greenhouse(http_json(url), board.company)


def parse_lever(payload: list, company: str) -> list[dict]:
    jobs = []
    for item in payload:
        categories = item.get("categories") or {}
        locations = [categories.get("location") or "", *(categories.get("allLocations") or [])]
        if item.get("country"):
            locations.append(item["country"])
        sections = [item.get("descriptionPlain") or ""]
        for block in item.get("lists") or []:
            sections.append(block.get("text", ""))
            sections.append(html_to_text(block.get("content", "")))
        sections.append(item.get("additionalPlain") or "")
        jobs.append(
            _job(
                title=item.get("text", ""),
                company=company,
                location="; ".join(dict.fromkeys(part for part in locations if part)),
                job_url=item.get("hostedUrl", ""),
                date_posted=iso_date(item.get("createdAt")),
                description="\n\n".join(part for part in sections if part)[:MAX_DESCRIPTION_CHARS],
                is_remote=item.get("workplaceType") == "remote",
            )
        )
    return jobs


def fetch_lever(board: Board) -> list[dict]:
    host = "api.eu.lever.co" if board.extra.get("region") == "eu" else "api.lever.co"
    return parse_lever(http_json(f"https://{host}/v0/postings/{board.slug}?mode=json"), board.company)


def parse_ashby(payload: dict, company: str) -> list[dict]:
    jobs = []
    for item in payload.get("jobs", []):
        if item.get("isListed") is False:
            continue
        address = ((item.get("address") or {}).get("postalAddress") or {})
        locations = [
            item.get("location") or "",
            *[(s or {}).get("location", "") for s in item.get("secondaryLocations") or []],
            address.get("addressLocality") or "",
            address.get("addressCountry") or "",
        ]
        jobs.append(
            _job(
                title=item.get("title", ""),
                company=company,
                location="; ".join(dict.fromkeys(part for part in locations if part)),
                job_url=item.get("jobUrl", ""),
                date_posted=iso_date(item.get("publishedAt")),
                description=(item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml", "")))[
                    :MAX_DESCRIPTION_CHARS
                ],
                is_remote=bool(item.get("isRemote")),
            )
        )
    return jobs


def fetch_ashby(board: Board) -> list[dict]:
    return parse_ashby(
        http_json(f"https://api.ashbyhq.com/posting-api/job-board/{board.slug}"), board.company
    )


def parse_smartrecruiters_list(payload: dict, company: str, slug: str) -> list[dict]:
    jobs = []
    for item in payload.get("content", []):
        location = item.get("location") or {}
        parts = [
            location.get("fullLocation") or "",
            location.get("city") or "",
            (location.get("country") or "").upper(),
        ]
        job = _job(
            title=item.get("name", ""),
            company=company,
            location="; ".join(dict.fromkeys(part for part in parts if part)),
            job_url=f"https://jobs.smartrecruiters.com/{slug}/{item.get('id', '')}",
            date_posted=iso_date(item.get("releasedDate")),
            is_remote=bool(location.get("remote")),
        )
        job["_detail_url"] = item.get("ref", "")
        jobs.append(job)
    return jobs


def parse_smartrecruiters_detail(payload: dict) -> str:
    sections = ((payload.get("jobAd") or {}).get("sections") or {}).values()
    return html_to_text("".join(f"<h3>{s.get('title', '')}</h3>{s.get('text', '')}" for s in sections))


def fetch_smartrecruiters(board: Board) -> list[dict]:
    jobs: list[dict] = []
    offset = 0
    while True:
        url = f"https://api.smartrecruiters.com/v1/companies/{board.slug}/postings?limit=100&offset={offset}"
        payload = http_json(url)
        page = parse_smartrecruiters_list(payload, board.company, board.slug)
        jobs.extend(page)
        offset += 100
        if not page or offset >= int(payload.get("totalFound", 0)):
            break
    _fill_details(
        jobs,
        lambda job: parse_smartrecruiters_detail(http_json(job["_detail_url"])) if job["_detail_url"] else "",
    )
    return jobs


def parse_workable(payload: dict, company: str) -> list[dict]:
    jobs = []
    for item in payload.get("jobs", []):
        places = [item, *(item.get("locations") or [])]
        parts = []
        for place in places:
            parts.extend([place.get("city") or "", place.get("country") or "", place.get("countryCode") or ""])
        jobs.append(
            _job(
                title=item.get("title", ""),
                company=company,
                location="; ".join(dict.fromkeys(part for part in parts if part)),
                job_url=item.get("url") or item.get("shortlink", ""),
                date_posted=iso_date(item.get("published_on") or item.get("created_at")),
                description=html_to_text(item.get("description", "")),
                is_remote=str(item.get("telecommuting")).lower() == "true",
            )
        )
    return jobs


def fetch_workable(board: Board) -> list[dict]:
    # The widget endpoint returns every job with its description in one GET;
    # the v3 search endpoint rate-limits (HTTP 429) almost immediately.
    url = f"https://apply.workable.com/api/v1/widget/accounts/{board.slug}?details=true"
    return parse_workable(http_json(url), board.company)


def parse_recruitee(payload: dict, company: str) -> list[dict]:
    jobs = []
    for item in payload.get("offers", []):
        locations = [item.get("location") or "", item.get("country_code") or ""]
        locations += [
            ", ".join(p for p in (loc.get("city"), loc.get("country")) if p)
            for loc in item.get("locations") or []
        ]
        jobs.append(
            _job(
                title=item.get("title", ""),
                company=company,
                location="; ".join(dict.fromkeys(part for part in locations if part)),
                job_url=item.get("careers_url", ""),
                date_posted=iso_date(item.get("published_at") or item.get("created_at")),
                description=html_to_text(
                    (item.get("description") or "") + (item.get("requirements") or "")
                ),
                is_remote=bool(item.get("remote")),
            )
        )
    return jobs


def fetch_recruitee(board: Board) -> list[dict]:
    host = board.extra.get("host") or f"{board.slug}.recruitee.com"
    return parse_recruitee(http_json(f"https://{host}/api/offers/"), board.company)


def _xml_text(element: ET.Element | None, tag: str) -> str:
    found = element.find(tag) if element is not None else None
    return (found.text or "").strip() if found is not None and found.text else ""


def parse_personio(xml_bytes: bytes, company: str, base_url: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    jobs = []
    for position in root.iter("position"):
        offices = [_xml_text(position, "office")]
        offices += [(o.text or "").strip() for o in position.findall("additionalOffices/office")]
        sections = []
        for block in position.findall("jobDescriptions/jobDescription"):
            sections.append(f"<h3>{_xml_text(block, 'name')}</h3>{_xml_text(block, 'value')}")
        job_id = _xml_text(position, "id")
        jobs.append(
            _job(
                title=_xml_text(position, "name"),
                company=company,
                location="; ".join(part for part in offices if part),
                job_url=f"{base_url}/job/{job_id}",
                date_posted=iso_date(_xml_text(position, "createdAt")),
                description=html_to_text("".join(sections)),
            )
        )
    return jobs


def fetch_personio(board: Board) -> list[dict]:
    domain = board.extra.get("domain", "jobs.personio.de")
    base_url = f"https://{board.slug}.{domain}"
    return parse_personio(http_get(f"{base_url}/xml", accept="application/xml"), board.company, base_url)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_bytes: bytes, company: str) -> list[dict]:
    """Jobs from an RSS 2.0 `<item>` or Atom `<entry>` feed (Teamtailor, Homerun, ...).

    Tags are matched by local name so any namespace works. Location comes from
    whichever of city/country/location/name tags the feed provides.
    """
    root = ET.fromstring(xml_bytes)
    entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    jobs = []
    for entry in entries:
        values: dict[str, list[str]] = {}
        link = ""
        parents = {child: parent for parent in entry.iter() for child in parent}
        for node in entry.iter():
            if node is entry:
                continue
            name = _local_name(node.tag)
            if name == "name":
                # <name> also labels departments; only a location's name is a place.
                if _local_name(parents[node].tag) not in {"location", "locations"}:
                    continue
            values.setdefault(name, []).append((node.text or "").strip())
            if name == "link" and not link:
                if node.get("href") and node.get("rel", "alternate") == "alternate":
                    link = node.get("href", "")
                elif (node.text or "").strip():
                    link = node.text.strip()
        locations = [
            v for key in ("city", "country", "location", "name") for v in values.get(key, []) if v
        ]
        description = next(
            (v[0] for key in ("description", "content", "summary") if (v := values.get(key)) and v[0]),
            "",
        )
        published = next(
            (v[0] for key in ("pubDate", "published", "updated") if (v := values.get(key)) and v[0]),
            "",
        )
        remote_status = " ".join(values.get("remoteStatus", []))
        jobs.append(
            _job(
                title=(values.get("title") or [""])[0],
                company=company,
                location="; ".join(dict.fromkeys(locations)),
                job_url=link,
                date_posted=iso_date(_rfc822_to_iso(published)),
                description=html_to_text(description),
                is_remote=remote_status.lower() in {"fully", "remote"},
            )
        )
    return jobs


def _rfc822_to_iso(value: str) -> str:
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return value


def _fetch_feed(url: str, company: str) -> list[dict]:
    return parse_feed(http_get(url, accept="application/rss+xml, application/atom+xml, application/xml"), company)


def fetch_teamtailor(board: Board) -> list[dict]:
    host = board.extra.get("host") or f"{board.slug}.teamtailor.com"
    return _fetch_feed(f"https://{host}/jobs.rss", board.company)


def fetch_homerun(board: Board) -> list[dict]:
    return _fetch_feed(f"https://feed.homerun.co/{board.slug}", board.company)


def fetch_rss(board: Board) -> list[dict]:
    return _fetch_feed(board.extra["url"], board.company)


WORKDAY_SEARCH_TERMS = (
    "site reliability",
    "SRE",
    "platform engineer",
    "devops",
    "infrastructure engineer",
    "cloud engineer",
    "systems engineer",
    "kubernetes",
    "production engineer",
)


def parse_workday_list(payload: dict) -> list[dict]:
    return [
        {"title": item.get("title", ""), "path": item.get("externalPath", ""), "location": item.get("locationsText", "")}
        for item in payload.get("jobPostings", [])
        if item.get("externalPath")
    ]


def parse_workday_detail(payload: dict, company: str) -> dict:
    info = payload.get("jobPostingInfo") or {}
    locations = [info.get("location") or "", *(info.get("additionalLocations") or [])]
    country = (info.get("country") or {}).get("descriptor") or ""
    locations.append(country)
    return _job(
        title=info.get("title", ""),
        company=company,
        location="; ".join(dict.fromkeys(part for part in locations if part)),
        job_url=info.get("externalUrl", ""),
        date_posted=iso_date(info.get("startDate")),
        description=html_to_text(info.get("jobDescription", "")),
        is_remote="remote" in str(info.get("remoteType", "")).lower(),
    )


def fetch_workday(board: Board) -> list[dict]:
    host, site = board.extra["host"], board.extra["site"]
    base = f"https://{host}/wday/cxs/{board.slug}/{site}"
    found: dict[str, dict] = {}
    for term in WORKDAY_SEARCH_TERMS:
        for offset in range(0, 200, 20):
            body = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term}
            page = parse_workday_list(http_json(f"{base}/jobs", body))
            for item in page:
                found.setdefault(item["path"], item)
            if len(page) < 20:
                break
    wanted = [item for item in found.values() if title_matches(item["title"])]
    jobs = []
    for item in wanted[:MAX_DETAIL_FETCHES]:
        jobs.append(parse_workday_detail(http_json(f"{base}{item['path']}"), board.company))
    return jobs


def parse_booking(payload: dict) -> list[dict]:
    jobs = []
    for entry in payload.get("jobs", []):
        item = entry.get("data") or {}
        jobs.append(
            _job(
                title=item.get("title", ""),
                company=item.get("hiring_organization") or item.get("brand") or "Booking.com",
                location=item.get("full_location") or ", ".join(
                    p for p in (item.get("city"), item.get("country")) if p
                ),
                job_url=f"https://jobs.booking.com/booking/jobs/{item.get('slug', '')}",
                date_posted=iso_date(item.get("posted_date") or item.get("create_date")),
                description=html_to_text(item.get("description", "")),
            )
        )
    return jobs


def fetch_booking(board: Board) -> list[dict]:
    jobs: list[dict] = []
    for page in range(1, 21):
        payload = http_json(f"https://jobs.booking.com/api/jobs?page={page}&location=Netherlands&limit=100")
        batch = parse_booking(payload)
        jobs.extend(batch)
        if not batch or len(jobs) >= int(payload.get("totalCount", 0)):
            break
    return jobs


def parse_capgemini(payload: dict) -> list[dict]:
    return [
        _job(
            title=item.get("title", ""),
            company="Capgemini" if (item.get("brand") or "Capgemini") == "Capgemini" else item["brand"],
            location=f"{item.get('location') or ''}, Netherlands".lstrip(", "),
            job_url=item.get("apply_job_url", ""),
            date_posted=iso_date(item.get("updated_at") or item.get("indexed_at")),
            description=html_to_text(item.get("description", "")),
        )
        for item in payload.get("data", [])
    ]


def fetch_capgemini(board: Board) -> list[dict]:
    url = "https://cg-jobstream-api.azurewebsites.net/api/job-search?page=1&size=1000&country_code=nl-nl"
    return parse_capgemini(http_json(url))


def parse_deloitte(payload: list, base_url: str) -> list[dict]:
    jobs = []
    for item in payload:
        cities = [c.get("name", "") for c in item.get("categories") or [] if c.get("parent") == "location"]
        job = _job(
            title=item.get("name", ""),
            company="Deloitte",
            location="; ".join([*cities, "Netherlands"]),
            job_url=urllib.parse.urljoin(base_url, item.get("slug", "")),
            date_posted=iso_date(item.get("datePosted") or item.get("publishedAt")),
        )
        job["_detail_url"] = job["job_url"]
        jobs.append(job)
    return jobs


def fetch_deloitte(board: Board) -> list[dict]:
    base_url = "https://werkenbijdeloitte.nl"
    jobs = parse_deloitte(http_json(f"{base_url}/data/jobpostings.json"), base_url)
    _fill_details(jobs, _describe_from_page)
    return jobs


def parse_optiver(payload: dict) -> list[dict]:
    jobs = []
    for item in payload.get("items", []):
        job = _job(
            title=item.get("title", ""),
            company="Optiver",
            location=item.get("location", ""),
            job_url=urllib.parse.urljoin("https://www.optiver.com", item.get("href", "")),
        )
        job["_detail_url"] = job["job_url"]
        jobs.append(job)
    return jobs


def fetch_optiver(board: Board) -> list[dict]:
    jobs: list[dict] = []
    for offset in range(0, 2000, 16):
        page = parse_optiver(http_json(f"https://www.optiver.com/en/api/v1/jobs?from={offset}"))
        if not page:
            break
        jobs.extend(page)
    _fill_details(jobs, _describe_from_page)
    return jobs


def parse_bamboohr_list(payload: dict, company: str, slug: str) -> list[dict]:
    jobs = []
    for item in payload.get("result", []):
        place = item.get("atsLocation") or {}
        city = (item.get("location") or {}).get("city") or place.get("city") or ""
        job = _job(
            title=item.get("jobOpeningName", ""),
            company=company,
            location="; ".join(p for p in (city, place.get("country") or "") if p),
            job_url=f"https://{slug}.bamboohr.com/careers/{item.get('id', '')}",
            is_remote=str(item.get("locationType")) == "1" or bool(item.get("isRemote")),
        )
        job["_id"] = item.get("id", "")
        jobs.append(job)
    return jobs


def fetch_bamboohr(board: Board) -> list[dict]:
    base = f"https://{board.slug}.bamboohr.com/careers"
    jobs = parse_bamboohr_list(http_json(f"{base}/list"), board.company, board.slug)

    def describe(job: dict) -> str:
        opening = (http_json(f"{base}/{job['_id']}/detail").get("result") or {}).get("jobOpening") or {}
        job["date_posted"] = iso_date(opening.get("datePosted"))
        return html_to_text(opening.get("description", ""))

    _fill_details(jobs, describe)
    return jobs


def parse_join(payload: dict, company: str, slug: str) -> list[dict]:
    jobs = []
    for item in payload.get("items", []):
        city = item.get("city") or {}
        country = item.get("country") or {}
        jobs.append(
            _job(
                title=item.get("title", ""),
                company=company,
                location="; ".join(
                    p for p in (city.get("cityName") or city.get("name"), country.get("name"), country.get("iso3166")) if p
                ),
                job_url=f"https://join.com/companies/{slug}/{item.get('idParam', '')}",
                date_posted=iso_date(item.get("createdAt")),
                is_remote=item.get("workplaceType") == "REMOTE",
            )
        )
    return jobs


def fetch_join(board: Board) -> list[dict]:
    company_id, slug = board.extra["company_id"], board.slug
    jobs: list[dict] = []
    for page in range(1, 100):
        payload = http_json(f"https://join.com/api/public/companies/{company_id}/jobs?page={page}&pageSize=5")
        jobs.extend(parse_join(payload, board.company, slug))
        if page >= int((payload.get("pagination") or {}).get("pageCount") or 0):
            break
    return jobs


def parse_gatsby_career(payload: dict, company: str, url: str) -> dict:
    career = ((payload.get("result") or {}).get("data") or {}).get("careers") or {}
    text = "\n\n".join(p for p in (career.get("description"), career.get("body")) if p)
    return _job(
        title=career.get("title", ""),
        company=company,
        location=career.get("location", ""),
        job_url=url,
        description=text[:MAX_DESCRIPTION_CHARS],
        is_remote=bool(REMOTE_PATTERN.search(text)),
    )


def fetch_gatsby(board: Board) -> list[dict]:
    """A Gatsby site: job URLs from the sitemap, each job's data from its page-data JSON."""
    origin = board.extra["origin"]
    sitemap = http_get(f"{origin}/sitemap-0.xml", accept="application/xml").decode("utf-8", "replace")
    urls = re.findall(rf"<loc>({re.escape(origin)}/careers/[^/<]+/)</loc>", sitemap)
    jobs = []
    for url in urls[:MAX_DETAIL_FETCHES]:
        slug = url.rstrip("/").rsplit("/", 1)[1]
        payload = http_json(f"{origin}/page-data/careers/{slug}/page-data.json")
        jobs.append(parse_gatsby_career(payload, board.company, url))
    return jobs


def _describe_from_page(job: dict) -> str:
    """Description from the job's own page (JSON-LD when present)."""
    markup = http_get(job["_detail_url"], accept="text/html").decode("utf-8", "replace")
    page = parse_html_job_page(markup, job["job_url"], job["title"], job["company"], "")
    if page["date_posted"] and not job["date_posted"]:
        job["date_posted"] = page["date_posted"]
    return page["description"]


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.json_ld: list[str] = []
        self._in_json_ld = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self._href, self._text = attributes["href"], []
        elif tag == "script" and (attributes.get("type") or "").lower() == "application/ld+json":
            self._in_json_ld = True
            self.json_ld.append("")

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, re.sub(r"\s+", " ", " ".join(self._text)).strip()))
            self._href = None
        elif tag == "script":
            self._in_json_ld = False

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
        if self._in_json_ld:
            self.json_ld[-1] += data


def _slug_title(href: str) -> str:
    """A readable title from a job URL's last path segment ("senior-devops-engineer")."""
    segment = urllib.parse.urlparse(href).path.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[-_]+", " ", urllib.parse.unquote(segment)).strip()


def parse_html_listing(markup: str, base_url: str, link_pattern: str = "") -> list[tuple[str, str]]:
    """(absolute url, title) for job links in the role family.

    A link counts when its text or its URL slug names a matching role: some
    pages put metadata rather than the title in the anchor. Hrefs that only
    appear inside embedded JSON (no real <a> tag) are picked up by their slug.
    """
    parser = _LinkExtractor()
    parser.feed(markup)
    anchors = list(parser.links)
    anchored = {href for href, _ in anchors}
    anchors += [
        (href, "") for href in re.findall(r'href=\\?"([^"\\]+)', markup) if href not in anchored
    ]
    pattern = re.compile(link_pattern) if link_pattern else None
    seen: dict[str, str] = {}
    for href, text in anchors:
        if pattern and not pattern.search(href):
            continue
        text = re.sub(r"\s*\b(?:View job|Bekijk vacature|Bekijken|Read more|Lees meer)\b\s*", " ", text).strip()
        slug = _slug_title(href)
        if title_matches(text):
            title = text
        elif title_matches(slug):
            title = slug
        else:
            continue
        url = urllib.parse.urljoin(base_url, href).split("#")[0]
        seen.setdefault(url, title)
    return list(seen.items())


def _job_postings(node) -> list[dict]:
    if isinstance(node, list):
        return [posting for child in node for posting in _job_postings(child)]
    if not isinstance(node, dict):
        return []
    kinds = node.get("@type")
    kinds = kinds if isinstance(kinds, list) else [kinds]
    found = [node] if "JobPosting" in kinds else []
    return found + _job_postings(node.get("@graph", []))


def _posting_location(posting: dict) -> str:
    places = posting.get("jobLocation") or []
    places = places if isinstance(places, list) else [places]
    parts = []
    for place in places:
        address = (place or {}).get("address") or {}
        if isinstance(address, str):
            parts.append(address)
            continue
        country = address.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        parts.extend(str(p) for p in (address.get("addressLocality"), country) if p)
    return "; ".join(dict.fromkeys(parts))


def _page_title(markup: str) -> str:
    """The job title from a page's <h1>, else the matching part of its <title>."""
    candidates = []
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", markup, re.IGNORECASE | re.DOTALL)
    if heading:
        candidates.append(html_to_text(heading.group(1)).replace("\n", " "))
    title = re.search(r"<title[^>]*>(.*?)</title>", markup, re.IGNORECASE | re.DOTALL)
    if title:
        # "Framer Careers: Senior SRE", "Senior SRE | Acme" -> the role part.
        candidates += [part.strip() for part in re.split(r"\s[|–—]\s|:\s", html.unescape(title.group(1)))]
    return next((c for c in candidates if title_matches(c)), "")


def parse_html_job_page(markup: str, url: str, fallback_title: str, company: str, default_location: str) -> dict:
    """One job from its own page: JSON-LD JobPosting when present, page text otherwise."""
    parser = _LinkExtractor()
    parser.feed(markup)
    for blob in parser.json_ld:
        try:
            postings = _job_postings(json.loads(blob))
        except json.JSONDecodeError:
            continue
        if postings:
            posting = postings[0]
            return _job(
                title=posting.get("title") or fallback_title,
                company=company,
                location=_posting_location(posting) or default_location,
                job_url=url,
                date_posted=iso_date(posting.get("datePosted")),
                description=html_to_text(html.unescape(str(posting.get("description") or ""))),
                is_remote=str(posting.get("jobLocationType", "")).upper() == "TELECOMMUTE",
            )
    return _job(
        title=_page_title(markup) or fallback_title,
        company=company,
        location=default_location,
        job_url=url,
        description=html_to_text(markup),
    )


def fetch_html(board: Board) -> list[dict]:
    listing_url = board.extra["url"]
    headers = board.extra.get("headers")
    raw = http_get(listing_url, accept="text/html, application/json", extra_headers=headers)
    markup = raw.decode("utf-8", "replace")
    if board.extra.get("json_key"):
        markup = json.loads(markup)[board.extra["json_key"]]
    markup = markup.replace("\\/", "/")  # hrefs embedded in escaped JSON
    links = parse_html_listing(markup, listing_url, board.extra.get("link_pattern", ""))
    jobs = []
    for url, text in links[:MAX_DETAIL_FETCHES]:
        page = http_get(url, accept="text/html").decode("utf-8", "replace")
        jobs.append(
            parse_html_job_page(page, url, text, board.company, board.extra.get("default_location", ""))
        )
    return jobs


def _fill_details(jobs: list[dict], describe: Callable[[dict], str]) -> None:
    """Fetch descriptions only for jobs that already pass both filters."""
    wanted = [j for j in jobs if title_matches(j["title"]) and location_matches(j["location"], j["is_remote"])]
    for job in wanted[:MAX_DETAIL_FETCHES]:
        try:
            job["description"] = describe(job)
        except Exception as exc:  # a missing description must not drop the job
            log.warning("  %s: description fetch failed for %s: %s", job["company"], job["job_url"], exc)


FETCHERS: dict[str, Fetcher] = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "workable": fetch_workable,
    "recruitee": fetch_recruitee,
    "personio": fetch_personio,
    "teamtailor": fetch_teamtailor,
    "workday": fetch_workday,
    "booking": fetch_booking,
    "homerun": fetch_homerun,
    "rss": fetch_rss,
    "capgemini": fetch_capgemini,
    "deloitte": fetch_deloitte,
    "optiver": fetch_optiver,
    "bamboohr": fetch_bamboohr,
    "join": fetch_join,
    "gatsby": fetch_gatsby,
    "html": fetch_html,
}


# ── Run ─────────────────────────────────────────────────────────────────────────


@dataclass
class BoardResult:
    board: Board
    seen: int = 0
    matched: list[dict] = field(default_factory=list)
    error: str = ""


def check_board(board: Board) -> BoardResult:
    result = BoardResult(board)
    try:
        jobs = FETCHERS[board.ats](board)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    result.seen = len(jobs)
    nl_only = bool(board.extra.get("nl_only"))
    matched = []
    for job in jobs:
        if not (job["job_url"] and title_matches(job["title"])):
            continue
        if nl_only:
            # Every role is in the Netherlands even where the feed does not say
            # so ("Headquarters", "Remote", or no location at all).
            if not location_matches(job["location"]):
                job["location"] = "; ".join(p for p in (job["location"], "Netherlands") if p)
        elif not location_matches(job["location"], job["is_remote"]):
            continue
        matched.append({k: v for k, v in job.items() if not k.startswith("_")})
    result.matched = matched
    return result


def check_boards(boards: list[Board]) -> list[BoardResult]:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(check_board, boards))


def failure_ratio_exceeded(results: list[BoardResult]) -> bool:
    """True when enough boards errored that the run should fail loudly."""
    if not results:
        return False
    failed = sum(1 for r in results if r.error)
    return failed / len(results) >= FAILURE_RATIO_LIMIT


def to_frame(results: list[BoardResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        for job in result.matched:
            rows.append({**job, "application_notes": f"source: career page ({result.board.ats})"})
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).drop_duplicates(subset=["job_url"], keep="first")
    frame = scraper.mark_title_mismatches(frame)
    # A title-mismatch verdict stands; every other role from a target company's
    # own career page goes straight to the apply queue without triage.
    frame.loc[frame["job_status"] == "", "job_status"] = config.ULTRA_SUITABLE_VALUE
    return frame


def log_summary(results: list[BoardResult], unsupported: list[Board]) -> None:
    log.info("%-28s %-16s %6s %8s  %s", "company", "source", "seen", "matched", "error")
    for r in sorted(results, key=lambda r: r.board.company.casefold()):
        log.info("%-28s %-16s %6d %8d  %s", r.board.company, r.board.ats, r.seen, len(r.matched), r.error)
    if unsupported:
        log.warning(
            "Not checked (no careers page readable without a browser): %s",
            ", ".join(b.company for b in unsupported),
        )


def select_boards(company: str | None) -> tuple[list[Board], list[Board]]:
    boards = BOARDS
    if company:
        boards = [b for b in BOARDS if b.company.casefold() == company.casefold()]
        if not boards:
            raise SystemExit(f"Unknown company '{company}'. See job_finder/company_boards.py.")
    supported = [b for b in boards if b.ats in FETCHERS]
    unsupported = [b for b in boards if b.ats not in FETCHERS]
    return supported, unsupported


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True, help="Country key from config.COUNTRIES")
    parser.add_argument("--company", help="Check one company from company_boards.BOARDS")
    parser.add_argument("--dry-run", action="store_true", help="Print matches; write nothing")
    args = parser.parse_args()

    scrape_main.configure_country(args.country)
    if not args.dry_run:
        scrape_main.validate_configs()

    supported, unsupported = select_boards(args.company)
    log.info("Checking %d career page(s) …", len(supported))
    results = check_boards(supported)
    log_summary(results, unsupported)
    jobs = to_frame(results)

    if args.dry_run:
        for _, job in jobs.iterrows():
            status = f" [{job['job_status']}]" if job.get("job_status") else ""
            print(f"{job['company']}: {job['title']} — {job['location']}{status}\n    {job['job_url']}")
        print(f"\n{len(jobs)} matching role(s); nothing written (dry run).")
    elif not jobs.empty:
        rows_written, rows_skipped, new_jobs = sheets.push_jobs(jobs, dedup_company_title=True)
        log.info("Written: %d  |  Skipped (dupes): %d", rows_written, rows_skipped)
        messages = scrape_main.build_messages(new_jobs, rows_written, SOURCE_LABEL)
        if messages:
            await telegram_bot.send(messages)
    else:
        log.info("No matching roles on any career page.")

    if failure_ratio_exceeded(results):
        failed = [r.board.company for r in results if r.error]
        print(f"❌ {len(failed)}/{len(results)} career pages failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)
    log.info("Done ✓")


if __name__ == "__main__":
    asyncio.run(main())
