# Current Sheet Example

Copy this file to `current-sheet.md` locally and fill in the real spreadsheet metadata.
`current-sheet.md` is ignored because it can contain private sheet IDs, URLs, tab IDs, and row counts.

## Spreadsheet

- Title: `YOUR_SHEET_TITLE`
- ID: `YOUR_SPREADSHEET_ID`
- URL: `https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit`
- Time zone: `Asia/Tehran`

## Tabs

| Tab | sheetId | Observed columns |
| --- | ---: | ---: |
| Denmark | 0 | 16 |

## Observed Headers

```text
scraped_at, me_applyed, me_result, title, location, company,
company_industry, job_level, job_type, is_remote, min_amount, max_amount,
currency, date_posted, job_url, description
```

## Application Submission Columns

- `applied_at`: datetime of a successful application submission.
- `application_notes`: confirmation text, submitted URL, or blocker details.
