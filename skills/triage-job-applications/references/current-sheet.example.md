# Current Sheet Example

Copy this file to `current-sheet.md` locally and fill in the real spreadsheet metadata.
`current-sheet.md` is ignored because it can contain private sheet IDs, URLs, tab IDs, and row counts.

Record the observation date at the top and refresh metadata and headers before making any edits.

## Spreadsheet

- Title: `YOUR_SHEET_TITLE`
- ID: `YOUR_SPREADSHEET_ID`
- URL: `https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit`
- Time zone: `YOUR_TIME_ZONE`

## Archive Spreadsheet

- Title: `YOUR_ARCHIVE_SHEET_TITLE`
- ID: `YOUR_ARCHIVE_SPREADSHEET_ID`
- Config key: `GOOGLE_ARCHIVE_SHEET_ID`
- Tabs: one per country, created on first archive.

`Not Suitable` rows are moved here by `python -m job_finder.cleanup --country
<name> --archive-unsuitable` and then deleted from the live sheet. Every column
is carried over including the full `description`.

**The archive header must stay identical to the live header — no archive-only
columns.** Dedup (`sheets.get_known_urls`) and the market report (`pull.py`) both
read this spreadsheet as well as the live one, and neither runs with
`GOOGLE_ARCHIVE_SHEET_ID` unset.

## Tabs

| Tab | sheetId | Observed columns | Rows |
| --- | ---: | ---: | ---: |
| Denmark | 0 | 20 | 0 |

## Observed Headers

The full 20-column schema written by `job_finder` is:

```text
scraped_at, job_status, application_result, title, location, company,
company_industry, job_level, job_type, is_remote, min_amount, max_amount,
currency, date_posted, job_url, description, cover_letter_path,
suitability_reason, applied_at, application_notes
```

The first 16 columns are the scraper's base schema. The last four are output
columns. A tab that predates them will be missing some; the skills add each one
to the right of `description` when they first need it.

## Application Submission Columns

- `cover_letter_path`: absolute path to the cover letter, written when the submit skill generates or reuses one for a form that asks for it.
- `suitability_reason`: the triage skill's visible reason for `Suitable` / `Not Suitable`.
- `applied_at`: datetime of a successful application submission, formatted `YYYY-MM-DD HH:mm <sheet time zone>`.
- `application_notes`: confirmation text, submitted URL, or blocker details.

Keep `job_status` as the triage/suitability column. Do not use it as a boolean applied marker once `applied_at` exists.
