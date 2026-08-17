---
name: gmail-job-application-reconcile
description: Reconcile job-application messages sitting in the Gmail Inbox with a Jobs! Google Sheet by classifying application outcomes, updating the application_result column, and filing the messages under the Apply! label. Mail already labelled Apply! is treated as processed and is never re-read. Use when the user asks to read recent or unread job emails, sync application statuses to the jobs tracker, or move application mail out of Inbox.
---

# Reconcile job-application email

Read recent application mail, match it to the user's jobs tracker, update only defensible outcomes, and organize the messages in Gmail. Treat the mailbox and sheet as live systems: inspect current state before writing and verify every write.

## Workflow

1. Determine scope.

   - **Scan the Inbox only.** Messages already carrying `Apply!` are processed and out of scope: never re-read them, never re-derive a status from them, and never revisit a row solely because of one. Filing a message under `Apply!` is what marks it done.
   - Use the user's requested window or count. If unspecified, use the last 14 days.
   - Search with Gmail syntax such as `in:inbox newer_than:14d -in:spam -in:trash -in:sent -in:draft`.
   - Both bounds are needed. `Apply!` alone does not bound the scan: the Inbox never empties, because only job mail is ever filed and everything else — newsletters, receipts, account notices — stays there permanently. Dropping the date window means re-reading hundreds of unrelated messages on every run, and that number only grows.
   - Read messages in full before classifying them; do not classify from snippets alone. Batch the reads if your tools support it — check your agent's tool-routing file, since not every setup has a batch read.
   - Consequence to accept: a rejection whose earlier receipt was already filed still lands in the Inbox, so outcomes keep flowing in. What is lost is the back-check over filed mail, so a status the previous run got wrong or missed stays wrong. Report a row as unmatched rather than reaching into `Apply!` for context.

2. Classify messages.

   - `Resume Reject`: explicit rejection or non-progression language.
   - `Online Meeting`: an actual invitation or scheduling request for a call/interview. Do not use this for messages that merely mention an interview process, a possible future next stage, or an interview guide.
   - `Resume Send`: explicit receipt, submission, or application confirmation.
   - Treat `under review` as `Resume Send` when the matched message clearly confirms that the application was received/submitted for the exact role and company. Do not classify generic career updates or role-closure notices this way.
   - Keep application-workflow messages such as candidate-account activation available for Gmail filing, but do not write `Resume Send` unless the message confirms an application was submitted.
   - Exclude LinkedIn invitations, profile-view notices, saved-job alerts, job newsletters, career-marketing mail, and unrelated personal or promotional messages.
   - Use the detailed phrase guidance in [email-status-and-matching.md](references/email-status-and-matching.md).

3. Read the tracker.

   - The tracker is the user's existing `Jobs!` spreadsheet. Its id and service-account
     path are already configured in the repo — do not search for it, and never create a
     new one.
   - Run `scripts/pull_rows.py`. It writes three files to `.reconcile_tmp/`:
     `rows.json` (every row, matching columns only), `by_url.json` (job URL and
     LinkedIn posting id → row), and `gaps.json` (rows marked `Applied` with a blank
     result). Search those files instead of re-reading the sheet per lookup.
   - `gaps.json` is the worklist. A row there is an application whose outcome was
     never recorded, so it is where an unmatched message most likely belongs.
   - The allowed values for `application_result` are exactly `Resume Send`,
     `Resume Reject`, and `Online Meeting`.
   - In the default tracker `application_result` is column C, `title` D, `company` F,
     and `job_url` O — but resolve columns by header name, not by letter. The scripts
     already do.

4. Match messages to rows conservatively.

   - Prefer a validated job URL plus matching company/title. Treat LinkedIn URLs cautiously because an email can contain recommended-job links; do not rely on a URL alone when several links are present.
   - Otherwise require exact or near-exact company and title evidence in the subject/body. Normalize punctuation, HTML entities, casing, and common separators before comparison.
   - If multiple rows share a company/title, use location, job URL, explicit role wording, and an existing application result to disambiguate. If evidence remains ambiguous, leave the sheet unchanged and report it.
   - Do not infer a row merely from a generic title such as “DevOps Engineer.”
   - When several messages map to one row, use the newest dated outcome. A later rejection supersedes an older receipt; an older receipt must never overwrite a newer rejection or meeting invitation.

5. Update the sheet.

   - Write the decided changes to a JSON file and apply them with
     `scripts/write_results.py`. Each item needs `tab`, `row`, `value`, `company`, and
     — where known — `title` and a short `why`.
   - Run it once with no flag and read the diff, then again with `--commit`. Without
     the flag it writes nothing.
   - The script enforces this step's rules in code: it re-reads each target cell,
     skips cells already holding the value, resolves `application_result` by header
     name, sends one `batchUpdate` of one-cell `updateCells` requests with
     `fields: "userEnteredValue"`, and reads every changed cell back afterwards.
   - It aborts the whole batch when a row's `company` does not match the sheet. That
     is a stale row number, not a bad value — the user edits the sheet by hand and the
     archiver deletes rows, so a coordinate can go stale between matching and writing.
     Re-run `pull_rows.py` and re-match rather than forcing the write.
   - Do not alter `job_status`, titles, URLs, notes, or formatting as part of this
     workflow.

6. File Gmail messages after classification.

   - Add the exact user label `Apply!` and remove `INBOX` from relevant application messages, using the labelling tools named in your agent's tool-routing file.
   - Never create the label. If `Apply!` does not exist, stop and report it rather than creating one with a similar name — `Apply`, `apply`, and `Apply!` are three different labels.
   - Moving mail requires explicit user intent. A direct request to move or organize the messages is authorization; for a read-only request, show the candidates and ask before changing labels.
   - It is acceptable to file a relevant application-workflow message that has no unambiguous tracker row, but do not invent a sheet status for it.

7. Verify and report.

   - Confirm the final value of every changed cell. `write_results.py --commit` prints this read-back itself; if the sheet was written another way, do it by hand.
   - Confirm no filed message is still in the Inbox. Search `in:inbox has:userlabels` and expect nothing — do not express this as a `label:` query, which can silently return an empty result whether or not the mail is there. This is the run's exit condition, since an application message left in the Inbox will be re-processed next run and one filed under `Apply!` never will be.
   - Report the Inbox messages read, messages filed, rows changed, and any ambiguous/unmatched messages. Link the updated spreadsheet.

## Tool routing

### Mail

This skill does not name mail tools. Tool names differ per agent and go stale
faster than the workflow does, so find your own: list what is available and match
it against the capabilities below.

| Capability | Used in |
| --- | --- |
| List labels and resolve the `Apply!` label id | steps 1, 6 |
| Search the mailbox with Gmail query syntax | steps 1, 7 |
| Read one message in full | step 2 |
| Add a label to a message, and remove `INBOX` from it | step 6 |

Confirm all four before starting. If any is missing, say so and stop — a partial
run that classifies mail it cannot then file leaves the Inbox as the next run's
worklist and quietly repeats itself. Do not substitute a browser: the matching
rules turn on exact message ids, and a rendered page does not give them.

Do not assume a batch form exists. Filing may cost two calls per message.

Read [gmail-and-linkedin-quirks.md](references/gmail-and-linkedin-quirks.md)
before step 1 — it covers a search syntax that fails silently, messages too large
to read directly, and how to get a role and posting id out of one.

### Tracker

Not a connector question: the sheet is reached through this repo's own service
account, and it is already configured. Use the scripts.

| Need | Use |
| --- | --- |
| Read rows for matching | `scripts/pull_rows.py` |
| Write results | `scripts/write_results.py` |
| Anything else | `job_finder.sheets.get_spreadsheet()` |

```bash
python skills/gmail-job-application-reconcile/scripts/pull_rows.py
python skills/gmail-job-application-reconcile/scripts/write_results.py changes.json
python skills/gmail-job-application-reconcile/scripts/write_results.py changes.json --commit
```

Spreadsheet id and service-account path resolve through `job_finder.config`
(environment first, then the git-ignored `config_local.py` at the repo root), so
neither script takes configuration and both work from any directory. If you find
yourself hunting for a Drive or Sheets tool, stop — that is not the route here.

Keep mail message ids and sheet row coordinates separate. Never pass a subject,
thread id, display URL, or placeholder string where a message id is required.
