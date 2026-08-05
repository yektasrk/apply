# Codex Browser and Worker-Pool Notes

These instructions are Codex-specific implementation guidance. The parent skill remains tool-neutral, but the six-slot rolling-pool invariants are mandatory.

## Browser surface

- Use the connected external Chrome control surface and the user's existing signed-in session. Follow the installed Chrome-control skill before browser work and reuse its existing browser binding.
- Keep every active application in one external Chrome window. Do not move application work to the in-app Browser.
- Use the connected Google Drive/Sheets tools for sheet metadata and reads. Route writes through the shared updater; use Chrome for application pages, not as the primary sheet-editing surface.
- When a LinkedIn job exposes `Apply on company website`, read the exact destination from the visible link and navigate the same worker-owned tab to that destination. Do not create a second application tab or duplicate an application through LinkedIn and the employer site.

## Default six-slot rolling pool

Use this pattern for every run; do not wait for explicit batch or parallel wording:

1. Refresh the sheet, identify the requested queue, and seed at most six eligible rows. If the host exposes fewer workers or the user requests fewer, use the smaller number.
2. Assign one stable worker per active row and freeze a coordinator mapping of worker, row, company, role, URL, Chrome tab, Chrome group, and state. Use the URL as the stable row key and never assign a row twice.
3. Keep exactly one live application tab per occupied worker. Put it in an expanded one-tab group named `Apply — <Role> — <Worker> — R<n>`; use the actual worker name or a stable fallback such as `Agent 1`. Keep every active group visible in the same Chrome window. Resolve apply-link URLs and navigate the existing tab directly whenever a click may spawn a popup. After every navigation or click, audit that worker's tabs immediately; retain the live application tab and close any displaced listing or stale tab before another interaction or slot assignment. At full capacity, do not trigger a transition that cannot remain in the current tab.
4. Navigate, fill, review, and confirm in that same owned tab. Do not pre-open queued jobs. If the site creates a child tab, preserve the needed state in one owned tab and close the extra so live application tabs never exceed occupied workers or six total.
5. Let independent workers continue when another reaches review or a blocker. A worker at `ready for review`, `awaiting user answer`, CAPTCHA, login handoff, or temporary failure keeps its row, tab, group, and slot.
6. Accept a user message that approves or reports manual submission for one or several active jobs. Resolve every named company, role, or row against the mapping and process only those jobs; ask for clarification only if a target is ambiguous.
7. Treat a broad command to run or continue the queue as fill permission only. Require job-specific approval before every final submit, while allowing one approval message to name several active jobs.
8. For user-authorized agent submission, click the final control and inspect the resulting state. For user-reported manual submission, inspect the matching live tab. A user message such as `submitted` is not evidence by itself; require a confirmation page, success message, application ID, submitted-state URL, or matched employer acknowledgement.
9. Keep the owning worker assigned while its outcome is written through the shared updater and the full row is read back. Serialize writes when several jobs finish together. A slot is not free until the target fields match and every unrelated field remains unchanged.
10. After verified recording, close the completed tab and remove its group. Then let the same worker re-refresh the sheet, claim the next eligible row, open one new tab, and create a newly named group. Never reuse an old tab for a different job while its prior outcome is unverified.
11. For a terminal closed or unsuitable row, record and verify the terminal outcome before recycling. For a resumable blocker, recycle only after the user explicitly abandons or skips it and the required note is recorded.

## Visibility and handoff

- Treat six as both the worker ceiling and the live application-tab ceiling. Browser-internal pages, helper searches, and confirmation pages must not become persistent extra tabs; use the worker's owned tab whenever possible.
- Keep all active groups expanded at handoff so the user can see every application. Preserve exactly the occupied workers' tabs, including review and CAPTCHA tabs.
- Use the Chrome tab-finalization call with every occupied worker tab in the keep list, and make it the final browser action of the turn. Do not omit a blocked or incomplete tab.
- Report the mapping of worker, group, row, company, role, state, and required user action so the user can approve several jobs unambiguously in one message.

## Codex interaction discipline

- Before every click, fill, select, or press, use the latest DOM snapshot, build a locator from visible state, and verify the locator count. After navigation or a meaningful action, take a fresh targeted snapshot before making the next decision.
- Scope repeated controls such as `Yes`, `No`, `Upload`, `Calendar`, and `Submit` to the relevant field or section. Do not use positional locators unless the count and the visible order make the position unambiguous.
- For resume upload controls, distinguish the autofill upload from the resume attachment upload. Use the file chooser on the resume control, then wait for and verify the uploaded filename/status.
- When writing a result to the sheet, re-read `application_result`, `applied_at`, and `cover_letter_path` immediately beforehand so user edits are not overwritten. Use the row's actual sheet ID and tab ID, not a browser URL or guessed tab name.

## Mandatory Codex Google Sheets write safeguards

Treat every Codex sheet mutation as destructive until it has been verified. These rules are mandatory and must never be skipped:

- Never send a Google Sheets `updateCells` request with an open-ended `GridRange`. Every request MUST include explicit `startRowIndex`, `endRowIndex`, `startColumnIndex`, and `endColumnIndex`. For a one-cell write, the range must be exactly one cell: `endRowIndex = startRowIndex + 1` and `endColumnIndex = startColumnIndex + 1`.
- A one-cell `rows` payload does not make an open-ended range safe. Missing end indexes are invalid for this workflow; stop and fix the request before sending it.
- Re-read the target rows immediately before every write. Resolve rows by normalized `job_url` (the stable key), then confirm the current row number, title, company, `job_status`, `application_result`, `cover_letter_path`, and `applied_at` still match the candidate mapping. Never trust a row number carried over from an earlier turn or stale snapshot.
- Capture a full pre-write snapshot of every target row (`A:T` or the complete documented row width), including all non-target fields. Do not write until the snapshot and the intended target URL agree.
- Prefer separate exact 1x1 writes for independent fields such as `job_status`, `application_result`, `applied_at`, and `application_notes`. If writing a multi-cell range, bound it exactly to the intended rectangle and provide every cell value in that rectangle.
- After every write, immediately re-read the full affected row(s) and verify both sides: target fields equal the intended values, and every non-target field is byte-for-byte unchanged from the pre-write snapshot. If any URL, title, company, description, cover-letter path, or other non-target value changes, stop all further writes and do not release or refill any worker slot.
- If a write response is ambiguous, a target URL disappears, rows appear to shift, or a read-back does not match the snapshot, treat the operation as failed. Do not attempt a repair using stale row numbers; re-scan the sheet by job URL, preserve the last known snapshot, and ask for recovery direction if the original row cannot be located.
- Never use a sheet write that sorts, inserts, deletes, or otherwise changes row order as part of application recording. Re-resolve by URL after any external sheet refresh or user edit.
- When recording user-confirmed submissions, apply the same pre-read, exact-range write, and full-row read-back checks. User confirmation authorizes the status update but does not waive spreadsheet integrity checks.
