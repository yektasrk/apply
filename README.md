# LinkedIn Job Scraper → Google Sheets + Telegram

Scrapes LinkedIn jobs on a schedule, appends new listings to a Google Sheet,
and sends a summary message to a Telegram channel.

---

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 2. Google Sheets — Service Account setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts** → Create a Service Account
5. Under **Keys**, click **Add Key → JSON** — download the file
6. Rename it to `service_account.json` and place it in this folder. This file is local-only and ignored by Git.
7. Open your Google Sheet → click **Share** → paste the service account email (looks like `xxx@xxx.iam.gserviceaccount.com`) → give it **Editor** access
8. Copy `.env.example` to `.env` and set `GOOGLE_SHEET_NAME` to the exact name of your spreadsheet
9. Copy the Sheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/**SHEET_ID_HERE**/edit`

---

## 3. Telegram Bot setup

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts — copy the **token**
3. Paste the token into `TELEGRAM_BOT_TOKEN` in `.env` locally or into GitHub Secrets for Actions
4. Add the bot to your channel as an **Administrator**
5. Set `TELEGRAM_CHANNEL_ID`:
   - Public channel: `"@your_channel_name"`
   - Private channel: numeric ID like `"-1001234567890"`
     (forward a message from the channel to @userinfobot to get the ID)

---

## 4. Configure your search

Search terms and country metadata live in `job_finder/config.py`. Secrets and personal paths live in local environment variables:

```bash
cp .env.example .env
# edit .env, then export it before running locally
set -a
source .env
set +a
```

> **Tip:** Keep `.env`, `service_account.json`, `resume.md`, PDFs, `raw/`, `wiki/`, and `cover_letters/` local. They are ignored by Git.

`AI_MATCHING_REQUIRED=true` fails fast when OpenAI matching cannot run. GitHub Actions sets it to `false` so scraping can still write new jobs when OpenAI quota is temporarily unavailable.

---

## 5. Run

```bash
python -m job_finder.main --country denmark
```

---

## 6. Automate (optional)

### macOS / Linux — cron (daily at 9 AM)
```bash
crontab -e
# add:
0 9 * * * cd /path/to/apply && python -m job_finder.main --country denmark >> scraper.log 2>&1
```

### Windows — Task Scheduler
Create a task that runs `python -m job_finder.main --country denmark` in the project directory.

### GitHub Actions (free cloud runner)
```yaml
# .github/workflows/scrape.yml
name: LinkedIn Scraper
on:
  schedule:
    - cron: "0 9 * * *"   # 9 AM UTC daily
  workflow_dispatch:        # also allows manual trigger

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m job_finder.main --country denmark
        env:
          SEARCH_TERM: "Python Developer"
          LOCATION: "United States"
          GOOGLE_SERVICE_ACCOUNT_FILE: service_account.json
          GOOGLE_SHEET_NAME: "LinkedIn Jobs"
          GOOGLE_SHEET_ID: ${{ secrets.GOOGLE_SHEET_ID }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHANNEL_ID: ${{ secrets.TELEGRAM_CHANNEL_ID }}
```
Store `service_account.json` contents as a GitHub secret and write it to disk
in a step before running.

---

## 7. Dealing with LinkedIn rate limits (429 errors)

LinkedIn blocks scrapers aggressively. Recommended mitigations:

- **Add proxies** in `job_finder/config.py`:
  ```python
  PROXIES = ["user:pass@1.2.3.4:8000"]
  ```
- **Lower `RESULTS_WANTED`** — stick to ≤50 per run
- **Increase `HOURS_OLD`** so you're not re-scraping everything
- **Add a delay** — run once per day, not every few minutes
- **Use a residential proxy service** (e.g. Bright Data, Oxylabs)

---

## File structure

```
apply/
├── job_finder/
│   ├── main.py           # Scheduled scrape entry point
│   ├── add_job.py        # Manual single-job entry point
│   ├── config.py         # App settings
│   ├── scraper.py        # LinkedIn scraping
│   ├── sheets.py         # Google Sheets writes
│   ├── ai_matcher.py     # Resume/job compatibility
│   └── telegram_bot.py   # Telegram notifications
├── requirements.txt      # pip dependencies
├── .env.example          # environment template without secrets
├── service_account.json  # Google Service Account key (local/ignored)
├── resume.md             # local/ignored
├── raw/                  # local/ignored source evidence
├── wiki/                 # local/ignored maintained knowledge
├── cover_letters/        # local/ignored generated letters
└── README.md
```
