# Apply

Apply is a private job-search automation workspace. It scrapes LinkedIn jobs by
country, appends deduped rows to Google Sheets, sends a Telegram summary, and
keeps local-only candidate material out of Git.

The tracked Python app lives in `job_finder/`. Personal data such as CVs, raw
evidence, the maintained wiki, generated cover letters, `.env`, and Google
service account keys are intentionally ignored.

## Repository Contents

```text
apply/
├── job_finder/                 # Python package for scraping and sheet writes
│   ├── main.py                 # Scheduled scrape entry point
│   ├── add_job.py              # Add one LinkedIn job URL manually
│   ├── check_availability.py   # Mark closed existing jobs in Google Sheets
│   ├── config.py               # Countries and env-backed runtime settings
│   ├── scraper.py              # LinkedIn scraping through JobSpy
│   ├── sheets.py               # Google Sheets dedupe and append logic
│   ├── telegram_bot.py         # Telegram notification helper
│   └── retries.py              # Shared retry policy
├── .github/workflows/          # Scheduled and manual GitHub Actions runs
├── .codex/skills/              # Project-specific Codex skills
├── AGENTS.md                   # Workspace rules for Codex/wiki work
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
5. Share the target Google Sheet with the service account email as an editor.
6. Set `GOOGLE_SHEET_ID` in `.env` from the sheet URL.
7. Set `GOOGLE_SHEET_NAME` if you want to keep the sheet name documented in env.

The app writes to country-specific tabs defined in `job_finder/config.py`.

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
`--tab`, or `--gid`. When a job URL is clearly closed, it writes `Closed` to
`me_applyed`, including rows currently marked `Suitable` or `Not Suitable`. It
leaves applied/rejected terminal statuses alone unless run with `--force`.

Supported country keys are currently `netherlands`, `germany`, `uk`, `denmark`,
`ireland`, `sweden`, `switzerland`, `portugal`, and `france`.

## GitHub Actions

The workflow in `.github/workflows/scrape-countries.yml` runs on GitHub-hosted
Python 3.13 runners. It can be triggered manually with a `country` input, and it
also runs on this UTC schedule. Each run first checks existing rows for that
country and marks closed jobs in `me_applyed`, then scrapes and appends new jobs.

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
```

Use `AVAILABILITY_CHECK_LIMIT` to cap the number of existing rows checked per
run, and `AVAILABILITY_CHECK_SLEEP` to add delay between URL checks.

## Local Knowledge Base

This workspace also supports a Codex-maintained local wiki:

- `raw/` stores immutable source material.
- `wiki/` stores maintained markdown knowledge.
- `cover_letters/` stores generated application material.

These folders are ignored by Git because they contain personal candidate data.
Project instructions and reusable Codex skills are tracked in `AGENTS.md` and
`.codex/skills/`.
