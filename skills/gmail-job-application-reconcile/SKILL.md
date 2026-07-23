---
name: gmail-job-application-reconcile
description: Reconcile recent Gmail job-application messages with a Jobs! Google Sheet by classifying application outcomes, updating the application_result column, and filing relevant messages under the Apply! label. Use when the user asks to read recent, unread, or Apply!-folder job emails, sync application statuses to the jobs tracker, or move application mail out of Inbox.
---

# Reconcile job-application email

Read recent application mail, match it to the user's jobs tracker, update only defensible outcomes, and organize the messages in Gmail. Treat the mailbox and sheet as live systems: inspect current state before writing and verify every write.

## Workflow

1. Determine scope.

   - Use the user's requested window or count. If unspecified, use the last 14 days and include messages already carrying `Apply!`.
   - Search broadly with Gmail syntax such as `newer_than:14d -in:spam -in:trash`; search the `Apply!` label separately using its exact label ID from `gmail_list_labels`.
   - Read full messages in batches with `gmail_batch_read_email`; do not classify from snippets alone.

2. Classify messages.

   - `Resume Reject`: explicit rejection or non-progression language.
   - `Online Meeting`: an actual invitation or scheduling request for a call/interview. Do not use this for messages that merely mention an interview process, a possible future next stage, or an interview guide.
   - `Resume Send`: explicit receipt, submission, or application confirmation.
   - Keep application-workflow messages such as candidate-account activation available for Gmail filing, but do not write `Resume Send` unless the message confirms an application was submitted.
   - Exclude LinkedIn invitations, profile-view notices, saved-job alerts, job newsletters, career-marketing mail, and unrelated personal or promotional messages.
   - Use the detailed phrase guidance in [email-status-and-matching.md](references/email-status-and-matching.md).

3. Locate the tracker.

   - Prefer the user's existing `Jobs!` Google Sheet. Search Drive if the spreadsheet ID is not already known; do not create a new tracker when an existing one is available.
   - Read spreadsheet metadata first. Confirm tab names, sheet IDs, row bounds, and the header row.
   - In the default tracker, `application_result` is column C, `title` is D, `company` is F, and `job_url` is O. The allowed values are exactly `Resume Send`, `Resume Reject`, and `Online Meeting`.
   - Read bounded ranges only. For large tabs, fetch the columns needed for matching rather than the entire grid.

4. Match messages to rows conservatively.

   - Prefer a validated job URL plus matching company/title. Treat LinkedIn URLs cautiously because an email can contain recommended-job links; do not rely on a URL alone when several links are present.
   - Otherwise require exact or near-exact company and title evidence in the subject/body. Normalize punctuation, HTML entities, casing, and common separators before comparison.
   - If multiple rows share a company/title, use location, job URL, explicit role wording, and an existing application result to disambiguate. If evidence remains ambiguous, leave the sheet unchanged and report it.
   - Do not infer a row merely from a generic title such as “DevOps Engineer.”
   - When several messages map to one row, use the newest dated outcome. A later rejection supersedes an older receipt; an older receipt must never overwrite a newer rejection or meeting invitation.

5. Update the sheet.

   - Immediately before writing, re-read every target `application_result` cell with `formattedValue`, `userEnteredValue`, and validation metadata.
   - Write only cells whose value should change. Use one precise Sheets `batchUpdate` containing `updateCells` requests with a one-cell range and `fields: "userEnteredValue"`.
   - Do not alter `job_status`, titles, URLs, notes, or formatting as part of this workflow.

6. File Gmail messages after classification.

   - Apply the exact user label `Apply!` and remove `INBOX` from relevant application messages with `gmail_apply_labels_to_emails`.
   - Use `create_missing_labels: false`; if `Apply!` does not exist, stop and report the issue rather than creating a similarly named label.
   - Moving mail requires explicit user intent. A direct request to move or organize the messages is authorization; for a read-only request, show the candidates and ask before changing labels.
   - It is acceptable to file a relevant application-workflow message that has no unambiguous tracker row, but do not invent a sheet status for it.

7. Verify and report.

   - Re-read all changed cells and confirm their final values.
   - Search for the intersection of `Apply!` and `INBOX` for the processed set; it should be empty.
   - Report the time window, messages read, messages filed, rows changed, and any ambiguous/unmatched messages. Link the updated spreadsheet.

## Tool routing

Use the connected Gmail and Google Drive/Sheets tools, not browser scraping, for mailbox and spreadsheet data:

- Gmail: `gmail_list_labels`, `gmail_search_emails`, `gmail_batch_read_email`, `gmail_apply_labels_to_emails`.
- Sheets: `google_drive_search`, `google_drive_get_spreadsheet_metadata`, `google_drive_get_spreadsheet_cells`, `google_drive_batch_update_spreadsheet`.

Keep Gmail message IDs and Sheets row coordinates separate. Never pass subjects, thread IDs, display URLs, or placeholder strings where a Gmail message ID is required.
