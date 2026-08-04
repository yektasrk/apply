# Apply

Apply is a private job-search automation workspace. It scrapes LinkedIn jobs by
country, appends deduped rows to Google Sheets, sends a Telegram summary, and
keeps local-only candidate material out of Git.

The tracked Python app lives in `job_finder/`. Personal data such as CVs, raw
evidence, the maintained wiki, generated cover letters, `.env`, and Google
service account keys are intentionally ignored.

The project covers the complete flow from job discovery to application: scheduled
scraping feeds a shared Google Sheet, an agent skill triages the rows, and the
application skill fills forms — writing a tailored cover letter on demand when a
form asks for one — while pausing before the final submission for user review.

## Repository Contents

```text
apply/
├── job_finder/                 # Python package for scraping and sheet writes
│   ├── main.py                 # Scheduled scrape entry point
│   ├── add_job.py              # Add one LinkedIn job URL manually
│   ├── archive.py              # Archive spreadsheet: append rows, read known URLs
│   ├── check_availability.py   # Mark closed Suitable jobs in Google Sheets
│   ├── config.py               # Countries and env-backed runtime settings
│   ├── scraper.py              # LinkedIn scraping through JobSpy
│   ├── sheets.py               # Google Sheets dedupe and append logic
│   ├── telegram_bot.py         # Telegram notification helper
│   └── retries.py              # Shared retry policy
├── .github/workflows/          # Scheduled and manual GitHub Actions runs
├── skills/                     # Canonical tool-neutral agent skills
├── .codex/skills/              # Codex discovery mirror (symlinks into skills/)
├── .claude/skills/             # Claude discovery mirror (symlinks into skills/)
├── tests/                      # Scraper and availability-check tests
├── AGENTS.md                   # Shared workspace rules for agent/wiki work
├── CLAUDE.md                   # Claude-specific notes (imports AGENTS.md)
├── setup-agent-skills.sh       # Rebuilds both per-tool skill mirrors
├── serve_wiki.py               # Local wiki preview server
├── requirements.txt
├── .env.example
└── README.md
```

Ignored local-only paths include `service_account.json`, `.env`, `resume.md`,
CV PDFs, `raw/`, `wiki/`, and `cover_letters/`.

## Setup

Use Python 3.13 to match GitHub Actions.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create local configuration:

```bash
cp .env.example .env
set -a
source .env
set +a
```

## Google Sheets

1. Create or choose a Google Cloud project.
2. Enable the Google Sheets API and Google Drive API.
3. Create a service account and download its JSON key.
4. Save the key locally as `service_account.json`.
5. Create a second, empty spreadsheet to serve as the archive.
6. Share **both** sheets with the service account email as an editor. A
   share-link is not enough; a service account has no browser session and must
   be added by address.
7. Set `GOOGLE_SHEET_ID` and `GOOGLE_ARCHIVE_SHEET_ID` in `.env` from the sheet
   URLs. Both are required — see [Two Spreadsheets](#two-spreadsheets).
8. Set `GOOGLE_SHEET_NAME` if you want to keep the sheet name documented in env.

The app writes to country-specific tabs defined in `job_finder/config.py`.
Archive tabs of the same names are created on demand.

## Telegram

1. Create a bot with `@BotFather`.
2. Add the bot to the target channel as an administrator.
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID` in `.env`.

For a public channel, `TELEGRAM_CHANNEL_ID` can be `@channel_name`. For a
private channel, use the numeric channel ID.

## Configuration

The default countries and sheet tabs are in `job_finder/config.py`.
Runtime settings are environment-backed:

```bash
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
GOOGLE_SHEET_NAME=
GOOGLE_SHEET_ID=
GOOGLE_ARCHIVE_SHEET_ID=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=
SEARCH_TERMS='"Site Reliability Engineer","Platform Engineer","DevOps Engineer","Infrastructure Engineer"'
RESULTS_WANTED=50
HOURS_OLD=36
REMOTE_ONLY=false
JOB_TYPE=fulltime
FETCH_DESCRIPTION=true
PROXIES=
```

`SEARCH_TERMS` and `PROXIES` are comma-separated lists. Use `JOB_TYPE=` to pass
no job type filter.

After scraping and deduplicating, the job finder pre-marks titles containing a
configured whole-word keyword such as `AWS`, `Staff`, `Consultant`, `MLOps`, or
`Microsoft` as `Not Suitable`, with `title missmatch` in
`suitability_reason`. These rows are still written to the sheet so the filter
decision remains visible. The full list is configured in
`job_finder/config.py` as `TITLE_MISMATCH_KEYWORDS`.

## Run Locally

Scrape one configured country:

```bash
python -m job_finder.main --country denmark
```

Add one LinkedIn job URL manually:

```bash
python -m job_finder.add_job --country denmark https://www.linkedin.com/jobs/view/1234567890
```

Check existing sheet rows and mark closed jobs:

```bash
python -m job_finder.check_availability --dry-run
python -m job_finder.check_availability --sheet "https://docs.google.com/spreadsheets/d/.../edit?gid=..."
python -m job_finder.check_availability
python -m job_finder.check_availability --country denmark
python -m job_finder.check_availability --tab Denmark
python -m job_finder.check_availability --gid 711463063
```

The checker scans configured country tabs by default. If you pass a full Google
Sheets URL with `gid=...`, it checks that tab unless you also pass `--country`,
`--tab`, or `--gid`.

**Only rows marked `Suitable` are checked.** Those are the jobs you intend to
apply to, so theirs is the only availability that changes a decision. Untriaged
rows are left alone until they are triaged, and not-suitable rows belong in the
archive sheet. This is also what keeps the checker from erasing triage verdicts:
`job_status` has no separate availability field, so writing `Closed` overwrites
whatever was there, and `Suitable` is the only verdict worth replacing that way.

A row is skipped when its `job_status` is `Applied`, or when `application_result`
or `applied_at` is nonblank — an application exists even if `job_status` has not
caught up, and burying it under an availability result would lose a real outcome.
Those protections hold under `--force`, which otherwise widens the scan to every
row regardless of status.

Pending status changes are flushed after every 100 checked jobs by default, then
once more for the final partial batch. Use `--write-batch-size` to change the
checkpoint size.

Supported country keys are currently `netherlands`, `germany`, `uk`, `denmark`,
`ireland`, `sweden`, `switzerland`, `portugal`, and `france`.

The runtime requirements do not include the optional test runner. Install it
once if needed, then run the automated tests from the repository root:

```bash
python -m pip install pytest
python -m pytest tests -q
```

The availability checker only marks a row `Closed` when it finds a recognized
closed-posting signal. It supports dry runs and flushes changes to Sheets in
configurable batches. Use `--force` only when you intentionally want to scan
statuses outside `Suitable`; it cannot override the application-evidence guards.

## Two Spreadsheets

Job rows live in two Google Sheets, each with the same country tabs:

| Sheet | Env var | Holds |
| --- | --- | --- |
| Live | `GOOGLE_SHEET_ID` | untriaged rows, `Suitable` rows, and applications in flight |
| Archive | `GOOGLE_ARCHIVE_SHEET_ID` | `Not Suitable` rows, with every column including `description` |

The live sheet is the working set, kept small enough to actually work in. The
archive keeps the full history of rejections so no triage reasoning is lost.
Archived rows are removed from the live sheet, which makes two things mandatory:

- **Dedup reads both.** `sheets.get_known_urls()` unions the live tab with its
  archive counterpart. Without the archive half, the next scrape would treat
  every archived job as new and re-import all of them. `job_finder.archive`
  raises when `GOOGLE_ARCHIVE_SHEET_ID` is unset rather than silently scraping
  against the live sheet alone.
- **The report reads both.** `skills/report-job-market/scripts/pull.py` reads
  both spreadsheets and exits with an error if the archive id is missing. A
  live-only report would drop every archived rejection reason and make the
  market look far more receptive than it is.

The dedup lookback is derived from `HOURS_OLD` rather than hardcoded: a scrape
only returns postings newer than that, so anything archived longer ago cannot
reappear. At the default 36h the window is 7 days, and it cannot drift when
`HOURS_OLD` changes.

`job_finder/archive.py` provides the plumbing — creating country tabs, appending
rows with read-back verification, and collecting archived URLs. **The command
that actually moves rows is not built yet**, so nothing is archived today and
the archive sheet is empty.

## Sheet Status Contract

The main job columns are defined in `job_finder/sheets.py`. The agent workflow
uses these fields consistently:

| Column | Meaning |
| --- | --- |
| `job_status` | Suitability and lifecycle status such as `Suitable`, `Not Suitable`, `Closed`, or `Applied` |
| `suitability_reason` | Sheet-visible explanation for a suitability decision |
| `application_result` | Application outcome; confirmed submissions use `Resume Send` |
| `cover_letter_path` | Absolute path to the generated cover letter |
| `applied_at` | Sheet-local timestamp written after a confirmed submission |
| `application_notes` | Confirmation, blocker, or other application context |

Rows with a nonblank `application_result` are treated as already processed by
the application workflow. A confirmed submission sets both `job_status` to
`Applied` and `application_result` to `Resume Send`.

## GitHub Actions

The workflow in `.github/workflows/scrape-countries.yml` runs on GitHub-hosted
Python 3.13 runners. It can be triggered manually with a `country` input, and it
also runs on this UTC schedule. Each run resolves the target country, then runs
scraping and closed-job marking as separate jobs in parallel. The closed-job
marker writes `Closed` to `job_status` and is allowed to finish independently of
the scraper.

```text
00:00 netherlands
02:00 germany
04:00 uk
06:00 denmark
08:00 ireland
10:00 sweden
12:00 switzerland
14:00 portugal
16:00 france
```

Required repository secrets:

```text
GOOGLE_SERVICE_ACCOUNT_JSON
GOOGLE_SHEET_NAME
GOOGLE_SHEET_ID
TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL_ID
```

`GOOGLE_SERVICE_ACCOUNT_JSON` should contain the full JSON key content. The
workflow writes it to `service_account.json` at runtime.

Optional repository variables:

```text
AVAILABILITY_CHECK_LIMIT
AVAILABILITY_CHECK_SLEEP
AVAILABILITY_RATE_LIMIT_COOLDOWN
AVAILABILITY_WRITE_BATCH_SIZE
```

Use `AVAILABILITY_CHECK_LIMIT` to cap the number of existing rows checked per
run. Use `AVAILABILITY_CHECK_SLEEP` to control the delay between URL checks; the
GitHub Actions workflow defaults this to 3 seconds when the variable is unset.
Use `AVAILABILITY_RATE_LIMIT_COOLDOWN` to override the per-host cooldown after
HTTP 429 responses; the checker defaults this to 300 seconds.
Use `AVAILABILITY_WRITE_BATCH_SIZE` to control how many checked jobs each
write checkpoint covers; the workflow defaults this to 100.

## Agent Skills

The reusable skills in `skills/` are the agent layer on top of the Python
pipeline. `skills/` is the source of truth; `.codex/skills/` and
`.claude/skills/` are discovery mirrors. Rebuild the mirrors after adding or
removing a skill:

```bash
bash setup-agent-skills.sh
```

In Codex, invoke a skill with `$skill-name`. In Claude, describe the task in
natural language or name the skill directly. The available skills are:

| Skill | Use it for | Main outputs or safeguards |
| --- | --- | --- |
| `$triage-job-applications` | Review open Sheet rows against the resume, job descriptions, and available evidence | Writes `Suitable`/`Not Suitable` with a reason |
| `$submit-job-applications` | Apply to suitable rows with no application timestamp | Fills forms and uploads materials, generates a tailored `cover_letters/<Country>/<Company>.md` on demand when a form asks for one and records its path, stops at the final submit for review, and records `Applied`/`Resume Send` only after confirmed submission |
| `$report-job-market` | Analyze triaged rows, rejection reasons, demanded skills, and learning gaps | Rebuilds `wiki/queries/job-market-fit-report.md` with Mermaid charts; does not write back to Sheets |
| `$wiki-read` | Answer questions from accumulated local wiki knowledge | Reads `wiki/` and returns answers with local page citations without modifying the wiki by default |
| `$wiki-maintain` | Ingest a source or file a durable answer into the wiki | Updates source/topic/entity/query pages, `wiki/index.md`, and the append-only `wiki/log.md` |
| `$wiki-evolve` | Audit and improve wiki structure and health | Checks links, frontmatter, provenance, orphans, and contradictions; records repairs in `wiki/meta/health.md` and the index/log |

The application skills are intentionally sequential:

```text
scrape → triage → fill application (+ cover letter when the form asks) → user review → submit → record outcome
              └──────────────────── report market / maintain wiki ────────────────────┘
```

Triage and application skills use local-only candidate material such as
`resume.md`, performance-review evidence, `cover_letters/`, and wiki defaults.
They do not invent experience or answers, do not overwrite existing application
artifacts, and do not submit an application without the review gate unless the
user explicitly requests submission without review.

## Local Knowledge Base

This workspace also supports an agent-maintained local wiki:

- `raw/` stores immutable source material.
- `wiki/` stores maintained markdown knowledge.
- `cover_letters/` stores generated application material.

These folders are ignored by Git because they contain personal candidate data.
Project instructions and reusable agent skills are tracked in `AGENTS.md` and
`skills/`. The workspace works with both Codex and Claude: `AGENTS.md` is the
shared contract, `CLAUDE.md` adds Claude-specific notes, and
`setup-agent-skills.sh` mirrors the canonical `skills/` into `.codex/skills/`
and `.claude/skills/` so each tool discovers them from its own directory.

To preview the local wiki with rendered Markdown and Mermaid charts:

```bash
python serve_wiki.py
```

The server prints the local URL and automatically selects a nearby free port if
the default port is occupied. The wiki is local-only and is not part of the
tracked application data.
