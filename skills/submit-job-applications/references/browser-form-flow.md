# Browser Form Flow

## Form Loop

Use the same loop for single-page and multi-step application forms:

1. Inspect the visible form state, required markers, current step label, validation messages, and enabled buttons.
2. Fill every required field that has a supported answer.
3. Save or autosave only when the site requires it to continue.
4. Click the safest advancing control: `Next`, `Continue`, `Save and continue`, `Apply`, or `Submit application`.
5. After navigation or DOM changes, inspect the new state before entering more data.
6. If validation errors appear, fix fields only when the correct value is known from the approved sources.
7. Continue until a confirmation page, email-confirmation message, or submitted-state screen appears.

Do not treat an intermediate `Next` click as a submission. Only write `applied_at` after the site confirms the final application was submitted.

## Data Sources

Use stable values from `wiki/topics/job-application-form-defaults.md` first. Use `resume.md`, the current row, and the cover letter for job-specific content. Use performance-review markdown only if it is already in the workspace and directly relevant to a free-text prompt.

For dynamic free-text questions:

- Anchor the answer to the job's stated requirement.
- Use one or two truthful examples from the resume or cover letter.
- Keep answers concise unless the form gives a larger textarea and asks for detail.
- Do not add unsupported metrics, relocation statements, authorization claims, or company-specific praise.

## Common Field Handling

- Name, email, LinkedIn, education, current role, and current employer: use the wiki defaults.
- Resume/CV upload: upload `the local repository/the local CV file`.
- Cover letter text: paste the row's cover letter content as plain text. If the source is Markdown, remove Markdown headings only if they are formatting artifacts; preserve the letter text. If the source is PDF, extract the text before pasting.
- Cover letter file upload: upload the existing PDF when `cover_letter_path` points to one. If the site requires PDF/DOC upload and the cover letter is Markdown, create a simple PDF derivative next to the Markdown file and upload that derivative.
- Country/location fields: use only the stable default current location unless the form is asking for target job location.
- Work authorization, sponsorship, visa, notice period, salary, phone, street address, and demographic fields: use the wiki defaults when present; otherwise stop the row if required.
- Optional unknown fields: leave blank when the form allows it.
- Equal-opportunity fields: prefer `Prefer not to answer` or equivalent when available and when the wiki does not define a more specific answer.

## Blockers

Leave `applied_at` blank and record a concise blocker in `application_notes` when:

- The posting is closed, removed, or impossible to access.
- The site requires a login or account creation that is not already available in the browser session.
- A required personal/legal field lacks a stable default.
- A CAPTCHA, bot challenge, payment, or nonstandard consent blocks submission.
- The form requires a document type that cannot be produced safely from available files.
- The final submit button would attest to something unsupported or false.

## Confirmation Evidence

Before writing success to the sheet, capture enough evidence in notes to make the action auditable:

- Confirmation message or application ID when visible.
- Final URL when useful.
- Submitted company and role.
- Any important deviations, such as using a generated PDF derivative for a cover-letter upload.
