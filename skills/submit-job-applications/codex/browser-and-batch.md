# Codex Browser and Batch Notes

These instructions are Codex-specific implementation guidance. The parent skill remains tool-neutral.

## Browser surface

- Use the connected Chrome control surface when the task depends on the user's signed-in browser session, cookies, or existing tabs. Follow the installed Chrome-control skill before browser work and reuse its existing browser binding.
- Use the connected Google Drive/Sheets tools for sheet metadata, row selection, reads, and writes. Use the browser for application pages, not as the primary sheet-editing surface.
- When a LinkedIn job exposes `Apply on company website`, read the exact destination from the visible link and navigate the same application tab to that destination. Do not duplicate an application through LinkedIn and the employer site.

## Five-tab batch pattern

For an explicit batch request:

1. Refresh the sheet and select at most five eligible rows. Create a stable mapping of row number, company, role, URL, and application tab.
2. Create one Chrome tab per row, navigate each to the row's job URL, then follow the visible company-site apply route. Parallelize independent navigation and inspection, but fill each form from its own fresh page state.
3. Continue with the remaining tabs when one is blocked. Keep the blocked tab live and write its blocker to `application_notes`; do not mark it Applied.
4. Stop the batch when each row is either ready for review, awaiting a user answer, or blocked. Do not open a new batch until the user confirms the current one is finished/submitted.
5. If the user asks to keep tabs open, preserve all batch tabs as handoff tabs. Use the Chrome tab-finalization call with every batch tab in the keep list, and make that call the final browser action of the turn. Never omit a user-requested live tab because it is blocked or incomplete.

The user saying `submitted` is not evidence by itself. First inspect the relevant live tab for a confirmation page, success message, application ID, or submitted-state URL; only then update `job_status`, `application_result`, `applied_at`, and `application_notes` in the sheet.

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
- After every write, immediately re-read the full affected row(s) and verify both sides: target fields equal the intended values, and every non-target field is byte-for-byte unchanged from the pre-write snapshot. If any URL, title, company, description, cover-letter path, or other non-target value changes, stop all further writes and do not start the next batch.
- If a write response is ambiguous, a target URL disappears, rows appear to shift, or a read-back does not match the snapshot, treat the operation as failed. Do not attempt a repair using stale row numbers; re-scan the sheet by job URL, preserve the last known snapshot, and ask for recovery direction if the original row cannot be located.
- Never use a sheet write that sorts, inserts, deletes, or otherwise changes row order as part of application recording. Re-resolve by URL after any external sheet refresh or user edit.
- When recording user-confirmed submissions, apply the same pre-read, exact-range write, and full-row read-back checks. User confirmation authorizes the status update but does not waive spreadsheet integrity checks.
