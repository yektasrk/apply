"""
company_boards.py — The companies `career_pages` checks, and where each lists its jobs.

Each entry names the source the company's own careers page is built from:

- a public job-board feed (`greenhouse`, `lever`, `ashby`, `smartrecruiters`,
  `workable`, `recruitee`, `personio`, `teamtailor`, `workday`), identified by
  the company's `slug` on that board;
- `html`, a careers page the company hosts itself, read without a browser.
  `extra["url"]` is the listing page, `extra["link_pattern"]` optionally limits
  which links count as jobs, and `extra["default_location"]` is used when a job
  page does not state one;
- a company's own jobs API (`booking`, `capgemini`, `deloitte`, `optiver`), a
  `homerun`, `bamboohr` or `join` board, a generic `rss` feed (`extra["url"]`),
  or a `gatsby` site read from its sitemap (`extra["origin"]`);
- `unsupported`, a careers page that cannot be read without a browser (or
  none at all). It is listed so every run names it instead of dropping it.

`extra["nl_only"]` marks a source whose roles are all in the Netherlands even
when a posting says only "Headquarters", "Remote", or nothing.

`company` is spelled the way LinkedIn spells it, so the company+title dedup
recognises a role already imported from LinkedIn.

Scope: the Netherlands visa-sponsoring employers with Iranian staff, minus
US-owned companies, ASML and its suppliers, and traditional banks.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Board:
    company: str
    ats: str
    slug: str = ""
    extra: dict = field(default_factory=dict, hash=False)


BOARDS: list[Board] = [
    # ── Public job-board feeds ──────────────────────────────────────────────────
    Board("Adyen", "greenhouse", "adyen"),
    Board("AutoScout24", "greenhouse", "autoscout24"),
    Board("Backbase", "greenhouse", "workatbackbase"),
    Board("bol", "greenhouse", "bolcom"),
    Board("Catawiki", "greenhouse", "catawiki"),
    Board("Flow Traders", "greenhouse", "flowtraders"),
    Board("HousingAnywhere", "greenhouse", "housinganywhere"),
    Board("IMC Trading", "greenhouse", "imc"),
    Board("JetBrains", "greenhouse", "jetbrains"),
    Board("Mews", "greenhouse", "mewssystems"),
    Board("Nebius", "greenhouse", "nebius"),
    Board("Picnic Technologies", "greenhouse", "teampicnic"),
    Board("Schuberg Philis", "greenhouse", "schubergphilis"),
    Board("Vinted", "greenhouse", "vinteden"),
    Board("Albelli", "lever", "storiogroup"),  # now Storio Group
    Board("TomTom", "lever", "tomtom", {"region": "eu"}),
    # Every Bitvavo role is listed at "Headquarters", which is Amsterdam.
    Board("Bitvavo", "ashby", "bitvavo", {"nl_only": True}),
    Board("Douro Labs", "ashby", "dourolabs.xyz"),
    Board("Lightspeed Commerce", "ashby", "lightspeedhq"),
    Board("Mollie", "ashby", "mollie"),
    Board("Vio.com", "ashby", "vio"),
    Board("Coolblue", "smartrecruiters", "Coolblue"),
    Board("DataChef", "smartrecruiters", "DataChef"),
    Board("AG5", "workable", "ag5"),
    Board("GoodHabitz", "workable", "goodhabitz"),
    Board("AIHR", "recruitee", "aihr"),
    Board("bunq", "recruitee", "bunq"),
    Board("CM.com", "recruitee", "cmcom"),
    Board("Convious", "recruitee", "careersconvious"),
    Board("DPG Media", "recruitee", "dpgmedia"),
    Board("Dyflexis", "recruitee", "dyflexis"),
    Board("Eurail", "recruitee", "interrail"),  # rebranded to Interrail
    Board("Instapro", "recruitee", "instaprogroup"),
    Board("iO", "recruitee", "iodigital"),
    Board("Lunatech", "recruitee", "lunatech", {"host": "recruitment.lunatech.com"}),
    Board("Onramper", "recruitee", "onramper"),
    Board("Roamler", "recruitee", "roamlercareers"),
    Board("Rotate", "recruitee", "rotate"),
    Board("Speakap", "recruitee", "speakap3"),
    Board("Studocu", "recruitee", "studocujobs"),
    Board("Swisscom", "recruitee", "swisscom"),
    Board("TrueFullstaq", "recruitee", "truefullstaq"),
    Board("Xebia", "recruitee", "xebiacareers"),  # the Benelux board
    Board("Spectral", "personio", "spectral", {"domain": "jobs.personio.com"}),
    Board("BUX", "teamtailor", "getbux", {"host": "careers.getbux.com"}),
    Board("Dustin", "teamtailor", "dustin", {"host": "jobs.dustin.nl"}),
    Board("Leaseweb", "teamtailor", "leaseweb", {"host": "leaseweb.teamtailor.com"}),
    Board("ML6", "teamtailor", "ml6", {"host": "jobs.ml6.eu"}),
    Board("Sendcloud", "teamtailor", "sendcloud", {"host": "jobs.sendcloud.com"}),
    Board("Oneflow", "teamtailor", "oneflow", {"host": "career.oneflow.com"}),
    Board("StyleShoots", "teamtailor", "profoto", {"host": "career.profoto.com"}),  # now Profoto
    Board("Elsevier", "workday", "relx", {"host": "relx.wd3.myworkdayjobs.com", "site": "ElsevierJobs"}),
    Board(
        "Just Eat Takeaway.com",
        "workday",
        "takeaway",
        {"host": "takeaway.wd3.myworkdayjobs.com", "site": "JET-ECS-R"},
    ),
    Board("dé VakantieDiscounter", "homerun", "vakantiediscounter"),
    Board("Tiqets", "homerun", "tiqets"),
    Board("Castor", "bamboohr", "castoredc"),
    Board("Farm21", "join", "farm21", {"company_id": 33560}),
    # NN's Dutch careers portal; the /500 suffix is the item limit (default 20).
    Board("NN Group", "rss", extra={"url": "https://www.nn-careers.com/feeds/rss/500", "nl_only": True}),
    # ── Company-hosted job APIs ─────────────────────────────────────────────────
    Board("Booking.com", "booking"),
    Board("Capgemini", "capgemini", extra={"nl_only": True}),  # Dutch search incl. Sogeti
    Board("Deloitte", "deloitte", extra={"nl_only": True}),  # werkenbijdeloitte.nl
    Board("Optiver", "optiver"),
    Board("Assertive Yield", "gatsby", extra={"origin": "https://www.assertiveyield.com"}),
    # ── Careers pages read as HTML ──────────────────────────────────────────────
    Board(
        "IKEA",
        "html",
        extra={
            # The Radancy search, pre-filtered to the Netherlands, returns HTML in JSON.
            "url": "https://jobs.ikea.com/en/search-jobs/results?ActiveFacetID=2750405&CurrentPage=1&RecordsPerPage=500&Distance=50&RadiusUnitType=0&ShowRadius=False&IsPagination=False&FacetType=0&SearchResultsModuleName=Search+Results&SearchFiltersModuleName=Search+Filters&SortCriteria=0&SortDirection=0&SearchType=6&OrganizationIds=22908&FacetFilters%5B0%5D.ID=2750405&FacetFilters%5B0%5D.FacetType=2&FacetFilters%5B0%5D.Count=84&FacetFilters%5B0%5D.Display=Netherlands&FacetFilters%5B0%5D.IsApplied=true&FacetFilters%5B0%5D.FieldName=",
            "json_key": "results",
            "headers": {"X-Requested-With": "XMLHttpRequest"},
            "link_pattern": r"^/en/job/",
            "nl_only": True,
        },
    ),
    Board(
        "Code Nomads",
        "html",
        extra={
            "url": "https://www.codenomads.nl/career/",
            "link_pattern": r"codenomads\.nl/jobs/[^/]+/$",
            "nl_only": True,
        },
    ),
    Board(
        "Company.info Nederland",
        "html",
        extra={
            "url": "https://werkenbijcompanyinfo.nl/vacatures",
            "link_pattern": r"^/vacature/[a-z0-9-]+-\d+$",
            "nl_only": True,
        },
    ),
    Board(
        "Elfsquad",
        "html",
        extra={
            "url": "https://www.elfsquad.io/about-us/vacancies",
            "link_pattern": r"/(?:de/|nl/)?join-the-squad-[a-z0-9-]+$",
            "nl_only": True,
        },
    ),
    # Framer's roles are listed as "Remote"; the company is based in Amsterdam.
    Board(
        "Framer",
        "html",
        extra={"url": "https://www.framer.com/careers/", "link_pattern": r"^\./[a-z0-9-]+$", "nl_only": True},
    ),
    Board(
        "Neurolytics",
        "html",
        extra={
            "url": "https://neurolytics.ai/en/careers-at-neurolytics/",
            "link_pattern": r"neurolytics\.ai/careers-at-neurolytics/[a-z0-9-]+$",
            "nl_only": True,
        },
    ),
    Board(
        "NextPax",
        "html",
        extra={
            "url": "https://nextpax.com/about-us/careers",
            "link_pattern": r"^https://nextpax\.com/(?!contact-us)[a-z0-9-]+\?hsLang=en$",
            "nl_only": True,
        },
    ),
    # ── No machine-readable careers page (checked 2026-09-17) ───────────────────
    Board("5ahead", "unsupported"),  # jobs hard-coded in a JS bundle
    Board("ARP Digital", "unsupported"),  # no open-roles page; NL office unconfirmed
    Board("Container Solutions", "unsupported"),  # no careers page
    Board("El Niño", "unsupported"),  # Cloudflare bot challenge on every page
    Board("Marktplaats", "unsupported"),  # Adevinta WordPress feed, empty and unmapped
    Board("Mobiquity", "unsupported"),  # Cloudflare 403; now Hexaware
    Board("Momentum", "unsupported"),  # company website not identified
    Board("NewGlobe", "unsupported"),  # Cloudflare 403
    Board("nexxbiz", "unsupported"),  # jobs only on LinkedIn
    Board("TouchTribe", "unsupported"),  # vacancy site is offline
    Board("WeTransfer", "unsupported"),  # hires through Bending Spoons
]
