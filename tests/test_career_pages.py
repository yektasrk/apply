import json

import pandas as pd
import pytest

from job_finder import career_pages as cp
from job_finder import sheets
from job_finder.company_boards import BOARDS, Board


# ── Filters ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "title",
    [
        "Senior Site Reliability Engineer",
        "SRE (Compute)",
        "Platform Engineer - Observability",
        "Senior DevOps Engineer",
        "ML Infrastructure Engineer",
        "Cloud Engineer",
        "Systems Engineer (Linux)",
        "Backend Engineer, Managed Kubernetes",
        "Infrastructure Developer (Go)",
        "Senior Cloud Operations Engineer",
        "Cloud Native Engineer",
        "Senior Storage Engineer",
        "System Administrator",
    ],
)
def test_title_matches_role_family(title):
    assert cp.title_matches(title)


@pytest.mark.parametrize(
    "title",
    [
        "Backend Engineer",
        "Account Manager",
        "Engineering Manager, Platform",
        "Junior DevOps Engineer",
        "DevOps Internship",
        "SRE - Early Talent",
        "Director of Infrastructure Engineering",
        "Werkstudent DevOps",
        "Product Manager, Search Infrastructure",
        "Projectleider Vastgoed & Infrastructuur",
        "Sales Engineer, Cloud Infrastructure",
        "Team Assistant - Infrastructure",
        "Technical Writer (Infrastructure L3 Support Team)",
        "Presresponsibilities",  # "SRE" only as a substring
    ],
)
def test_title_rejects_other_roles(title):
    assert not cp.title_matches(title)


@pytest.mark.parametrize(
    "location, remote",
    [
        ("Amsterdam", False),
        ("Utrecht, Netherlands", False),
        ("Den Haag", False),
        ("NL", False),
        ("Berlin; Amsterdam, Netherlands", False),
        ("Remote - Europe", False),
        ("EMEA", True),
    ],
)
def test_location_matches_netherlands_or_remote_europe(location, remote):
    assert cp.location_matches(location, remote)


@pytest.mark.parametrize(
    "location, remote",
    [
        ("London, United Kingdom", False),
        ("Remote - United States", False),
        ("Remote", True),
        ("Berlin, Germany", False),
        ("online", False),  # lowercase "nl" inside a word is not the country code
    ],
)
def test_location_rejects_elsewhere(location, remote):
    assert not cp.location_matches(location, remote)


def test_html_to_text_keeps_blocks_drops_scripts_and_caps_length():
    text = cp.html_to_text("<p>One &amp; two</p><script>x()</script><ul><li>Three</li></ul>")
    assert text == "One & two\n\nThree"
    assert len(cp.html_to_text("<p>" + "a" * 60_000 + "</p>")) == cp.MAX_DESCRIPTION_CHARS


def test_iso_date_formats():
    assert cp.iso_date("2026-09-16T12:05:00+0000") == "2026-09-16"
    assert cp.iso_date(1711403416463) == "2024-03-25"
    assert cp.iso_date("") == ""


# ── Parsers ─────────────────────────────────────────────────────────────────────


def test_parse_greenhouse():
    payload = {
        "jobs": [
            {
                "title": " Senior  Platform Engineer ",
                "absolute_url": "https://job-boards.greenhouse.io/adyen/jobs/1",
                "location": {"name": "Amsterdam"},
                "offices": [{"name": "Amsterdam", "location": "Amsterdam"}],
                "first_published": "2026-09-01T07:58:55-05:00",
                "content": "&lt;p&gt;Run &amp;amp; build&lt;/p&gt;",
            }
        ]
    }
    (job,) = cp.parse_greenhouse(payload, "Adyen")
    assert job["title"] == "Senior Platform Engineer"
    assert job["location"] == "Amsterdam"
    assert job["date_posted"] == "2026-09-01"
    assert job["description"] == "Run & build"
    assert job["job_url"].endswith("/jobs/1")


def test_parse_lever():
    payload = [
        {
            "text": "DevOps Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/abc",
            "categories": {"location": "Amsterdam", "allLocations": ["Amsterdam", "Berlin"]},
            "country": "NL",
            "createdAt": 1711403416463,
            "workplaceType": "remote",
            "descriptionPlain": "Intro",
            "lists": [{"text": "You will", "content": "<li>Run k8s</li>"}],
            "additionalPlain": "Benefits",
        }
    ]
    (job,) = cp.parse_lever(payload, "Acme")
    assert job["location"] == "Amsterdam; Berlin; NL"
    assert job["is_remote"] is True
    assert job["description"] == "Intro\n\nYou will\n\nRun k8s\n\nBenefits"


def test_parse_ashby_skips_unlisted():
    payload = {
        "jobs": [
            {
                "title": "SRE",
                "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                "location": "Amsterdam",
                "secondaryLocations": [{"location": "Remote (EU)"}],
                "address": {"postalAddress": {"addressCountry": "Netherlands"}},
                "publishedAt": "2026-09-10T00:00:00Z",
                "descriptionPlain": "Text",
                "isRemote": False,
                "isListed": True,
            },
            {"title": "Hidden SRE", "isListed": False},
        ]
    }
    (job,) = cp.parse_ashby(payload, "Acme")
    assert job["location"] == "Amsterdam; Remote (EU); Netherlands"
    assert job["description"] == "Text"


def test_parse_smartrecruiters_list_and_detail():
    payload = {
        "content": [
            {
                "id": "744",
                "name": "Cloud Engineer",
                "releasedDate": "2026-09-02T10:00:00.000Z",
                "location": {"city": "Amsterdam", "country": "nl", "remote": False},
                "ref": "https://api.smartrecruiters.com/v1/companies/Acme/postings/744",
            }
        ],
        "totalFound": 1,
    }
    (job,) = cp.parse_smartrecruiters_list(payload, "Acme", "Acme")
    assert job["job_url"] == "https://jobs.smartrecruiters.com/Acme/744"
    assert job["location"] == "Amsterdam; NL"
    assert job["_detail_url"].endswith("/744")
    detail = {"jobAd": {"sections": {"jobDescription": {"title": "Role", "text": "<p>Run it</p>"}}}}
    assert cp.parse_smartrecruiters_detail(detail) == "Role\n\nRun it"


def test_parse_workable():
    payload = {
        "jobs": [
            {
                "title": "Platform Engineer",
                "url": "https://apply.workable.com/j/ABC123",
                "city": "Utrecht",
                "country": "Netherlands",
                "locations": [{"city": "Utrecht", "country": "Netherlands", "countryCode": "NL"}],
                "published_on": "2026-09-03",
                "telecommuting": False,
                "description": "<p>A</p><p>B</p>",
            }
        ]
    }
    (job,) = cp.parse_workable(payload, "Acme")
    assert job["job_url"] == "https://apply.workable.com/j/ABC123"
    assert job["location"] == "Utrecht; Netherlands; NL"
    assert job["description"] == "A\n\nB"
    assert job["is_remote"] is False


def test_parse_recruitee():
    payload = {
        "offers": [
            {
                "title": "DevOps Engineer",
                "careers_url": "https://careers.bunq.com/o/devops",
                "location": "Amsterdam, Netherlands",
                "country_code": "NL",
                "locations": [{"city": "Amsterdam", "country": "Netherlands"}],
                "published_at": "2026-09-15 08:11:57 UTC",
                "description": "<p>Desc</p>",
                "requirements": "<p>Req</p>",
                "remote": False,
            }
        ]
    }
    (job,) = cp.parse_recruitee(payload, "bunq")
    assert job["location"] == "Amsterdam, Netherlands; NL"
    assert job["date_posted"] == "2026-09-15"
    assert job["description"] == "Desc\n\nReq"


def test_parse_personio():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <workzag-jobs><position>
      <id>42</id><office>Amsterdam</office>
      <additionalOffices><office>Rotterdam</office></additionalOffices>
      <name>Site Reliability Engineer</name>
      <jobDescriptions><jobDescription><name>Tasks</name><value><![CDATA[<p>Keep it up</p>]]></value></jobDescription></jobDescriptions>
      <createdAt>2026-08-01T10:00:00+00:00</createdAt>
    </position></workzag-jobs>"""
    (job,) = cp.parse_personio(xml, "Acme", "https://acme.jobs.personio.de")
    assert job["job_url"] == "https://acme.jobs.personio.de/job/42"
    assert job["location"] == "Amsterdam; Rotterdam"
    assert job["description"] == "Tasks\n\nKeep it up"
    assert job["date_posted"] == "2026-08-01"


def test_parse_feed_teamtailor_rss():
    rss = b"""<?xml version="1.0"?>
    <rss xmlns:tt="https://teamtailor.com/locations"><channel><item>
      <title>Platform Engineer</title>
      <link>https://careers.acme.com/jobs/1-platform-engineer</link>
      <description>&lt;p&gt;Build&lt;/p&gt;</description>
      <pubDate>Tue, 15 Sep 2026 10:00:00 +0000</pubDate>
      <remoteStatus>hybrid</remoteStatus>
      <tt:locations><tt:location><tt:city>Amsterdam</tt:city><tt:country>Netherlands</tt:country></tt:location></tt:locations>
    </item></channel></rss>"""
    (job,) = cp.parse_feed(rss, "Acme")
    assert job["job_url"].endswith("1-platform-engineer")
    assert job["location"] == "Amsterdam; Netherlands"
    assert job["date_posted"] == "2026-09-15"
    assert job["description"] == "Build"
    assert job["is_remote"] is False


def test_parse_feed_homerun_atom_ignores_department_names():
    atom = b"""<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title type="text">DevOps Engineer</title>
      <link rel="alternate" href="https://jobs.tiqets.work/devops"/>
      <updated>2026-09-12T08:00:00Z</updated>
      <location><name>Amsterdam</name></location>
      <department><name>Engineering</name></department>
      <description>&lt;p&gt;Ship&lt;/p&gt;</description>
    </entry></feed>"""
    (job,) = cp.parse_feed(atom, "Tiqets")
    assert job["job_url"] == "https://jobs.tiqets.work/devops"
    assert job["location"] == "Amsterdam"
    assert job["date_posted"] == "2026-09-12"
    assert job["description"] == "Ship"


def test_parse_feed_plain_rss_without_location():
    rss = b"""<rss version="2.0"><channel><item>
      <title>Cloud Engineer</title><link>https://www.nn-careers.com/vacature/1/cloud</link>
      <pubDate>Mon, 14 Sep 2026 09:00:00 +0200</pubDate><description>Body</description>
    </item></channel></rss>"""
    (job,) = cp.parse_feed(rss, "NN Group")
    assert job["location"] == ""
    assert job["job_url"].endswith("/cloud")


def test_parse_workday_list_and_detail():
    listing = {"jobPostings": [{"title": "DevOps Engineer", "externalPath": "/job/NL/DevOps_R1", "locationsText": "2 Locations"}, {"title": "No path"}]}
    assert cp.parse_workday_list(listing) == [
        {"title": "DevOps Engineer", "path": "/job/NL/DevOps_R1", "location": "2 Locations"}
    ]
    detail = {
        "jobPostingInfo": {
            "title": "DevOps Engineer",
            "location": "Amsterdam",
            "additionalLocations": ["Leiden"],
            "country": {"descriptor": "Netherlands"},
            "startDate": "2026-09-16",
            "externalUrl": "https://acme.wd3.myworkdayjobs.com/Careers/job/NL/DevOps_R1",
            "jobDescription": "<p>Do ops</p>",
        }
    }
    job = cp.parse_workday_detail(detail, "Acme")
    assert job["location"] == "Amsterdam; Leiden; Netherlands"
    assert job["job_url"].startswith("https://acme.wd3")
    assert job["description"] == "Do ops"


def test_parse_booking():
    payload = {
        "jobs": [
            {
                "data": {
                    "slug": "30245",
                    "title": "Site Reliability Engineer II",
                    "full_location": "Amsterdam, Netherlands",
                    "hiring_organization": "Booking.com",
                    "posted_date": "2026-09-16T12:05:00+0000",
                    "description": "<p>Keep Booking up</p>",
                }
            }
        ],
        "totalCount": 1,
    }
    (job,) = cp.parse_booking(payload)
    assert job["job_url"] == "https://jobs.booking.com/booking/jobs/30245"
    assert job["company"] == "Booking.com"
    assert job["description"] == "Keep Booking up"


def test_parse_capgemini_uses_brand_as_company():
    payload = {
        "data": [
            {"title": "DevOps Engineer", "brand": "Sogeti", "location": "Utrecht", "apply_job_url": "https://c/1",
             "updated_at": "2026-09-14T16:41:21.000Z", "description": "<p>D</p>"},
            {"title": "SRE", "brand": "Capgemini", "location": "", "apply_job_url": "https://c/2"},
        ]
    }
    first, second = cp.parse_capgemini(payload)
    assert (first["company"], first["location"], first["date_posted"]) == ("Sogeti", "Utrecht, Netherlands", "2026-09-14")
    assert (second["company"], second["location"]) == ("Capgemini", "Netherlands")


def test_parse_deloitte():
    payload = [
        {
            "name": "Cloud Engineer ",
            "slug": "/vacature/cloud-engineer-ref1/",
            "datePosted": "2026-05-26T09:50:12.356Z",
            "categories": [{"name": "IT", "parent": "interests"}, {"name": "Amsterdam", "parent": "location"}],
        }
    ]
    (job,) = cp.parse_deloitte(payload, "https://werkenbijdeloitte.nl")
    assert job["title"] == "Cloud Engineer"
    assert job["location"] == "Amsterdam; Netherlands"
    assert job["job_url"] == "https://werkenbijdeloitte.nl/vacature/cloud-engineer-ref1/"
    assert job["_detail_url"] == job["job_url"]


def test_parse_optiver():
    (job,) = cp.parse_optiver(
        {"items": [{"title": "Linux Engineer", "location": "Amsterdam", "href": "/join-us/jobs/tech/amsterdam/linux/"}]}
    )
    assert job["job_url"] == "https://www.optiver.com/join-us/jobs/tech/amsterdam/linux/"
    assert job["location"] == "Amsterdam"


def test_parse_bamboohr_list():
    payload = {
        "result": [
            {"id": "45", "jobOpeningName": "SRE", "location": {"city": "Amsterdam"},
             "atsLocation": {"country": "Netherlands"}, "locationType": "0"},
            {"id": "46", "jobOpeningName": "DevOps", "location": {"city": None}, "atsLocation": {}, "locationType": "1"},
        ]
    }
    first, second = cp.parse_bamboohr_list(payload, "Castor", "castoredc")
    assert first["location"] == "Amsterdam; Netherlands"
    assert first["job_url"] == "https://castoredc.bamboohr.com/careers/45"
    assert second["is_remote"] is True


def test_parse_join():
    payload = {
        "items": [
            {"title": "Platform Engineer", "idParam": "123-platform", "createdAt": "2026-07-17T14:20:26Z",
             "city": {"cityName": "Delft"}, "country": {"name": "Netherlands", "iso3166": "NL"},
             "workplaceType": "HYBRID"}
        ]
    }
    (job,) = cp.parse_join(payload, "Farm21", "farm21")
    assert job["location"] == "Delft; Netherlands; NL"
    assert job["job_url"] == "https://join.com/companies/farm21/123-platform"


def test_parse_gatsby_career_detects_remote():
    payload = {"result": {"data": {"careers": {
        "title": "DevOps Engineer", "description": "Fully Remote", "body": "## Role", "location": "Europe"}}}}
    job = cp.parse_gatsby_career(payload, "Assertive Yield", "https://ay/careers/devops/")
    assert job["is_remote"] is True
    assert cp.location_matches(job["location"], job["is_remote"])
    assert job["description"] == "Fully Remote\n\n## Role"


def test_parse_html_listing_strips_button_text():
    markup = '<a href="/en/job/amsterdam/devops/1"><h2>DevOps Engineer</h2><span>View job</span></a>'
    links = cp.parse_html_listing(markup, "https://jobs.ikea.com/en/search", "")
    assert links == [("https://jobs.ikea.com/en/job/amsterdam/devops/1", "DevOps Engineer")]


def test_parse_html_listing_filters_by_text_and_pattern():
    markup = """
      <a href="/vacatures/devops-engineer">DevOps  Engineer</a>
      <a href="/vacatures/devops-engineer#apply">DevOps Engineer</a>
      <a href="/vacatures/sales">Sales Lead</a>
      <a href="/blog/devops-engineer-tips">DevOps Engineer tips</a>
    """
    links = cp.parse_html_listing(markup, "https://acme.nl/werken-bij", r"/vacatures/")
    assert links == [("https://acme.nl/vacatures/devops-engineer", "DevOps Engineer")]


def test_parse_html_listing_uses_slug_and_json_hrefs():
    markup = (
        '<a href="/careers/senior-devops-engineer">Full Time | Remote</a>'
        '<script>{"url":"<a href=\\"/join-the-squad-platform-engineer\\">"}</script>'
        '<a href="/careers/marketeer">Full Time</a>'
    )
    links = cp.parse_html_listing(markup, "https://acme.nl/", "")
    assert links == [
        ("https://acme.nl/careers/senior-devops-engineer", "senior devops engineer"),
        ("https://acme.nl/join-the-squad-platform-engineer", "join the squad platform engineer"),
    ]


def test_parse_html_job_page_prefers_json_ld():
    posting = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "JobPosting",
                "title": "Senior DevOps Engineer",
                "datePosted": "2026-09-05",
                "description": "&lt;p&gt;Automate&lt;/p&gt;",
                "jobLocation": {"@type": "Place", "address": {"addressLocality": "Utrecht", "addressCountry": "NL"}},
            }
        ],
    }
    markup = f'<html><script type="application/ld+json">{json.dumps(posting)}</script><p>Other</p></html>'
    job = cp.parse_html_job_page(markup, "https://acme.nl/v/1", "DevOps", "Acme", "")
    assert job["title"] == "Senior DevOps Engineer"
    assert job["location"] == "Utrecht; NL"
    assert job["description"] == "Automate"
    assert job["date_posted"] == "2026-09-05"


def test_parse_html_job_page_falls_back_to_page_text():
    job = cp.parse_html_job_page(
        "<html><style>x{}</style><h1>Join us</h1><p>Body</p></html>",
        "https://acme.nl/v/1",
        "DevOps Engineer",
        "Acme",
        "Netherlands",
    )
    assert job["title"] == "DevOps Engineer"  # "Join us" is not a role title
    assert job["location"] == "Netherlands"
    assert job["description"] == "Join us\n\nBody"
    page = cp.parse_html_job_page("<h1>Senior <b>Platform</b> Engineer</h1>", "u", "platform engineer", "Acme", "")
    assert page["title"] == "Senior Platform Engineer"
    page = cp.parse_html_job_page("<title>Framer Careers: Senior SRE</title>", "u", "x", "Framer", "")
    assert page["title"] == "Senior SRE"


# ── Run logic ───────────────────────────────────────────────────────────────────


def test_check_board_keeps_only_matching_roles(monkeypatch):
    jobs = [
        cp._job(title="SRE", company="Acme", location="Amsterdam", job_url="u1"),
        cp._job(title="SRE", company="Acme", location="London", job_url="u2"),
        cp._job(title="Sales", company="Acme", location="Amsterdam", job_url="u3"),
    ]
    jobs[0]["_detail_url"] = "internal"
    monkeypatch.setitem(cp.FETCHERS, "fake", lambda board: jobs)
    result = cp.check_board(Board("Acme", "fake"))
    assert result.seen == 3
    assert [j["job_url"] for j in result.matched] == ["u1"]
    assert "_detail_url" not in result.matched[0]


def test_check_board_nl_only_keeps_unlocated_roles(monkeypatch):
    jobs = [
        cp._job(title="SRE", company="Bitvavo", location="Headquarters", job_url="u1"),
        cp._job(title="SRE", company="Bitvavo", location="Amsterdam", job_url="u2"),
    ]
    monkeypatch.setitem(cp.FETCHERS, "fake", lambda board: jobs)
    result = cp.check_board(Board("Bitvavo", "fake", extra={"nl_only": True}))
    assert [j["location"] for j in result.matched] == ["Headquarters; Netherlands", "Amsterdam"]


def test_check_board_records_errors(monkeypatch):
    def boom(board):
        raise cp.HttpError(404, "https://x")

    monkeypatch.setitem(cp.FETCHERS, "fake", boom)
    result = cp.check_board(Board("Acme", "fake"))
    assert result.error == "HttpError: HTTP 404 for https://x"
    assert result.matched == []


def test_failure_ratio_threshold():
    ok = cp.BoardResult(Board("A", "greenhouse"))
    bad = cp.BoardResult(Board("B", "greenhouse"), error="boom")
    assert not cp.failure_ratio_exceeded([ok, ok, ok, bad])  # 25%
    assert cp.failure_ratio_exceeded([ok, ok, bad])  # 33%
    assert not cp.failure_ratio_exceeded([])


def test_to_frame_notes_source_and_premarks_titles():
    result = cp.BoardResult(
        Board("Acme", "lever"),
        matched=[
            cp._job(title="Platform Engineer", company="Acme", location="Amsterdam", job_url="u1"),
            cp._job(title="Staff Platform Engineer", company="Acme", location="Amsterdam", job_url="u2"),
            cp._job(title="Platform Engineer", company="Acme", location="Amsterdam", job_url="u1"),
        ],
    )
    frame = cp.to_frame([result])
    assert frame["job_url"].tolist() == ["u1", "u2"]
    assert set(frame["application_notes"]) == {"source: career page (lever)"}
    assert frame["job_status"].tolist() == ["⭐ Ultra Suitable", "Not Suitable"]


def test_select_boards_splits_unsupported(monkeypatch):
    boards = [Board("A", "greenhouse", "a"), Board("B", "unsupported")]
    monkeypatch.setattr(cp, "BOARDS", boards)
    assert cp.select_boards(None) == ([boards[0]], [boards[1]])
    assert cp.select_boards("b") == ([], [boards[1]])
    with pytest.raises(SystemExit):
        cp.select_boards("missing")


def test_registry_is_well_formed():
    names = [b.company.casefold() for b in BOARDS]
    assert len(names) == len(set(names)), "duplicate company in BOARDS"
    known = set(cp.FETCHERS) | {"unsupported"}
    for board in BOARDS:
        assert board.ats in known, board
        if board.ats in {"greenhouse", "lever", "ashby", "smartrecruiters", "workable", "workday"}:
            assert board.slug, board
        if board.ats == "workday":
            assert {"host", "site"} <= set(board.extra), board
        if board.ats == "html":
            assert board.extra.get("url"), board


# ── Cross-source dedup ──────────────────────────────────────────────────────────


def test_company_title_key_ignores_case_spacing_and_punctuation():
    assert sheets.company_title_key("Booking.com", "Site Reliability Engineer II") == sheets.company_title_key(
        "booking com", "site  reliability engineer ii"
    )
    assert sheets.company_title_key("Adyen", "SRE") != sheets.company_title_key("Adyen", "SRE II")


class _FakeWorksheet:
    title = "Netherlands"

    def __init__(self, headers, columns):
        self._headers = headers
        self._columns = columns

    def row_values(self, _row):
        return self._headers

    def batch_get(self, ranges):
        return self._columns


def test_read_company_title_keys_reads_only_two_columns():
    ws = _FakeWorksheet(
        ["scraped_at", "title", "company"],
        [[["Adyen"], ["Mollie"], []], [["SRE"], ["DevOps Engineer"], ["Orphan title"]]],
    )
    assert sheets.read_company_title_keys(ws) == {
        sheets.company_title_key("Adyen", "SRE"),
        sheets.company_title_key("Mollie", "DevOps Engineer"),
        sheets.company_title_key("", "Orphan title"),
    }
    assert sheets.read_company_title_keys(_FakeWorksheet(["job_url"], [])) == set()


def test_push_jobs_drops_company_title_duplicates(monkeypatch):
    ws = _FakeWorksheet(sheets.SHEET_COLUMNS, [])
    written = []
    monkeypatch.setattr(sheets, "get_worksheet", lambda: ws)
    monkeypatch.setattr(sheets, "ensure_header", lambda _ws: ["scraped_at"] + sheets.SHEET_COLUMNS)
    monkeypatch.setattr(sheets, "get_known_urls", lambda _ws: {"https://seen"})
    monkeypatch.setattr(
        sheets, "get_known_company_titles", lambda _ws: {sheets.company_title_key("Adyen", "SRE")}
    )
    monkeypatch.setattr(sheets, "_write_rows", lambda _ws, rows, _h: written.extend(rows))
    jobs = pd.DataFrame(
        {
            "title": ["SRE", "SRE", "Platform Engineer"],
            "company": ["Adyen", "Adyen", "Adyen"],
            "job_url": ["https://seen", "https://greenhouse/1", "https://greenhouse/2"],
        }
    )
    count, skipped, new = sheets.push_jobs(jobs, dedup_company_title=True)
    assert (count, skipped) == (1, 2)
    assert new["job_url"].tolist() == ["https://greenhouse/2"]
    assert len(written) == 1


def test_ultra_suitable_rows_get_availability_checks():
    from job_finder import check_availability

    assert check_availability._is_checkable("⭐ Ultra Suitable", force=False)
    assert check_availability._is_checkable(" Suitable ", force=False)
    assert not check_availability._is_checkable("Not Suitable", force=False)
