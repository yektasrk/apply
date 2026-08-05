# Apply

Apply is a private job-search automation workspace covering the full flow from
job discovery to application: scheduled scraping appends deduped LinkedIn rows to
a shared Google Sheet and sends a Telegram summary, an agent skill triages the
rows, and the application skill fills forms — writing a tailored cover letter on
demand — while pausing before the final submit for user review.

The tracked Python app lives in `job_finder/`. Personal material — CVs,
`resume.md`, `raw/`, `wiki/`, `cover_letters/`, `.env`, and
`service_account.json` — is intentionally Git-ignored.

## Repository Contents

```text
apply/
├── job_finder/            # Scraping, dedupe, sheet writes, availability checks
├── skills/                # Canonical tool-neutral agent skills (source of truth)
├── .codex/skills/         # Codex discovery mirror (symlinks into skills/)
├── .claude/skills/        # Claude discovery mirror (symlinks into skills/)
├── .github/workflows/     # Scheduled and manual scrape runs
├── tests/                 # Scraper and availability-check tests
├── AGENTS.md              # Shared workspace rules for agent/wiki work
├── CLAUDE.md              # Claude-specific notes (imports AGENTS.md)
├── setup-agent-skills.sh  # Rebuilds both per-tool skill mirrors
└── serve_wiki.py          # Local wiki preview server
```

## Setup

Use Python 3.13 to match GitHub Actions.

```bash
python3 -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill it in; every runtime setting is documented
there. `SEARCH_TERMS` and `PROXIES` are comma-separated lists, and `JOB_TYPE=`
passes no job type filter. Countries and their sheet tabs are defined in
`job_finder/config.py`.

### Google Sheets

1. Enable the Google Sheets API and Google Drive API in a Google Cloud project.
2. Create a service account, download its JSON key, and save it locally as
   `service_account.json`.
3. Create a second, empty spreadsheet to serve as the archive.
4. Share **both** sheets with the service account email as an editor. A
   share-link is not enough; a service account has no browser session and must
   be added by address.
5. Set `GOOGLE_SHEET_ID` and `GOOGLE_ARCHIVE_SHEET_ID` in `.env` from the sheet
   URLs. Both are required — see [Two Spreadsheets](#two-spreadsheets).

Country tabs are created on demand in both spreadsheets.

### Telegram

Create a bot with `@BotFather`, add it to the target channel as an
administrator, and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID`. For a
public channel the ID can be `@channel_name`; for a private one, use the numeric
ID.

## Run Locally

```bash
python -m job_finder.main --country denmark
python -m job_finder.add_job --country denmark https://www.linkedin.com/jobs/view/1234567890
python -m job_finder.check_availability --dry-run
python -m job_finder.check_availability --country denmark
```

The availability checker scans configured country tabs by default; `--tab`,
`--gid`, or a full sheet URL with `gid=...` narrows it to one tab. It only marks
a row `Closed` on a recognized closed-posting signal, and flushes pending writes
every `--write-batch-size` rows (default 100).

**Only rows marked `Suitable` are checked**, because `job_status` has no separate
availability field — writing `Closed` overwrites whatever verdict was there, and
`Suitable` is the only one worth replacing that way. A row is also skipped when
its status is `Applied` or when `application_result` or `applied_at` is nonblank,
so a real outcome is never buried under an availability result. Both protections
hold under `--force`, which otherwise widens the scan to every row.

Tests need the optional runner:

```bash
python -m pip install pytest && python -m pytest tests -q
```

## Two Spreadsheets

Job rows live in two Google Sheets, each with the same country tabs:

| Sheet | Env var | Holds |
| --- | --- | --- |
| Live | `GOOGLE_SHEET_ID` | untriaged rows, `Suitable` rows, and applications in flight |
| Archive | `GOOGLE_ARCHIVE_SHEET_ID` | `Not Suitable` rows, with every column including `description` |

The live sheet is the working set, kept small enough to actually work in; the
archive keeps the full history of rejections so no triage reasoning is lost.
Archived rows leave the live sheet, which makes two things mandatory:

- **Dedup reads both.** `sheets.get_known_urls()` unions the live tab with its
  archive counterpart; without the archive half the next scrape would re-import
  every archived job. `job_finder.archive` raises when
  `GOOGLE_ARCHIVE_SHEET_ID` is unset rather than silently scraping the live
  sheet alone.
- **The report reads both.** `skills/report-job-market/scripts/pull.py` errors
  out if the archive id is missing — a live-only report would drop every
  archived rejection reason and make the market look far more receptive than it
  is.

The dedup lookback derives from `HOURS_OLD` (7 days at the default 36h) rather
than being hardcoded, so it cannot drift when `HOURS_OLD` changes.

`job_finder/archive.py` provides the plumbing — country tabs, appends with
read-back verification, archived-URL collection. **The command that actually
moves rows is not built yet**, so nothing is archived today and the archive sheet
is empty.

## Sheet Status Contract

Columns are defined in `job_finder/sheets.py`. The agent workflow uses these
fields consistently:

| Column | Meaning |
| --- | --- |
| `job_status` | Suitability and lifecycle status: `Suitable`, `Not Suitable`, `Closed`, or `Applied` |
| `suitability_reason` | Sheet-visible explanation for a suitability decision |
| `application_result` | Application outcome; confirmed submissions use `Resume Send` |
| `cover_letter_path` | Absolute path to the generated cover letter |
| `applied_at` | Sheet-local timestamp written after a confirmed submission |
| `application_notes` | Confirmation, blocker, or other application context |

A nonblank `application_result` means the row is already processed. A confirmed
submission sets `job_status` to `Applied` and `application_result` to
`Resume Send`.

After scraping and dedupe, titles matching a configured whole-word keyword
(`TITLE_MISMATCH_KEYWORDS` in `job_finder/config.py`) are pre-marked
`Not Suitable` with `title missmatch` as the reason. Those rows are still written
so the filter decision stays visible.

## GitHub Actions

`.github/workflows/scrape-countries.yml` runs on Python 3.13 runners, on a
per-country UTC cron schedule defined in that file, and can be triggered manually
with a `country` input. Each run resolves the country, then runs scraping and
closed-job marking as parallel jobs.

Required secrets: `GOOGLE_SERVICE_ACCOUNT_JSON` (the full JSON key content,
written to `service_account.json` at runtime), `GOOGLE_SHEET_NAME`,
`GOOGLE_SHEET_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`.

Optional variables tune the availability check: `AVAILABILITY_CHECK_LIMIT` caps
rows checked per run, `AVAILABILITY_CHECK_SLEEP` sets the delay between URL
checks (workflow default 3s), `AVAILABILITY_RATE_LIMIT_COOLDOWN` overrides the
per-host cooldown after HTTP 429 (default 300s), and
`AVAILABILITY_WRITE_BATCH_SIZE` sets the write checkpoint size (default 100).

## Agent Skills

The skills in `skills/` are the agent layer on top of the Python pipeline;
`.codex/skills/` and `.claude/skills/` are discovery mirrors. Rebuild them after
adding or removing a skill:

```bash
bash setup-agent-skills.sh
```

Codex invokes a skill with `$skill-name`; in Claude, describe the task or name
the skill directly.

| Skill | Use it for |
| --- | --- |
| `triage-job-applications` | Review open rows against the resume and evidence; writes `Suitable`/`Not Suitable` with a reason |
| `submit-job-applications` | Apply to suitable rows: fills forms, uploads materials, generates a cover letter on demand, stops at the final submit for review, records the outcome only after confirmation |
| `report-job-market` | Analyze triaged rows, rejection reasons, demanded skills, and learning gaps into `wiki/queries/job-market-fit-report.md`; never writes back to Sheets |
| `wiki-read` | Answer questions from the local wiki with page citations, without modifying it |
| `wiki-maintain` | Ingest a source or file a durable answer; updates pages, `wiki/index.md`, and the append-only `wiki/log.md` |
| `wiki-evolve` | Audit links, frontmatter, provenance, orphans, and contradictions; records repairs in `wiki/meta/health.md` |

The application skills are intentionally sequential:

```text
scrape → triage → fill application (+ cover letter when the form asks) → user review → submit → record outcome
              └──────────────────── report market / maintain wiki ────────────────────┘
```

They use local-only candidate material, never invent experience or answers, do
not overwrite existing application artifacts, and never submit without the review
gate unless explicitly told to.

## Local Wiki

`raw/` stores immutable source material and `wiki/` the maintained markdown
knowledge layer; `AGENTS.md` is the full contract. To preview it with rendered
Markdown and Mermaid charts:

```bash
python serve_wiki.py
```

The server prints the local URL and picks a nearby free port if the default is
occupied.
