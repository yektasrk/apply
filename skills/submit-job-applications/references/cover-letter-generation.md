# Cover-Letter Generation

Cover letters are generated here, at apply time, not during triage. Generate one only when the application form actually asks for a cover letter (an upload field or a text box). Do not pre-generate letters for suitable rows whose forms never request one.

## When To Generate, Reuse, Or Skip

For a row whose form exposes a cover-letter field:

1. If `cover_letter_path` is nonblank and the file exists, reuse it. Do not overwrite or regenerate it. Upload or paste that existing letter.
2. Otherwise, generate a new letter following the rules below, validate it against the word band and quality bar before saving (revise until it passes — never save a letter that fails the band), save it locally, write its absolute path to `cover_letter_path` in the sheet immediately after saving, then upload or paste it.

If the form does not ask for a cover letter, do not generate one and leave `cover_letter_path` as it is.

Write the sheet path as soon as the letter is saved, even if the application is later blocked, left at the review gate, or not submitted. The saved file is kept regardless of the application outcome.

## Generation Boundary

You must write the cover-letter prose yourself after reading the full job description, resume, and any available performance-review evidence. Do not use scripts, local programs, external projects, or API generators to produce the prose.

Scripts and tools are allowed only for mechanical work: creating directories, saving text you authored to a file, checking file presence, checking word counts, extracting text from an existing PDF, creating a PDF derivative for upload, or writing the path back to the sheet.

Do not draft from excerpts alone. Read the complete job description for the row so the letter responds to the employer's real priorities.

## Where To Save

Save the Markdown letter under `cover_letters/<Country>/` at the repo root unless the user provides another destination. Use the sheet tab name as the country when available; otherwise infer the country from `location` or `COUNTRIES` in `job_finder/config.py`.

Use the filename `<Company>.md`, sanitized only for filesystem safety: keep the company spelling readable and close to the sheet value, replace path separators and unsafe characters, collapse repeated whitespace, and trim leading/trailing punctuation. Do not include the date, role, seniority, or long slugs. Avoid overwriting existing files; if the same company already has a different Markdown cover letter in that country folder, append a short numeric suffix such as `<Company>-2.md`.

For example, a generated letter for Kamstrup in the Denmark tab is saved as `cover_letters/Denmark/Kamstrup.md` and stored in the sheet as its absolute path. Existing PDFs in a country folder are historical application artifacts; do not edit or rename them.

## Evidence Handling

Use the resume as a compact factual baseline, not as the main prose source. Do not copy resume bullet points into the letter.

When performance reviews are available, read them and use them as factual context only when their origin is reliable; follow [performance-review-evidence.md](performance-review-evidence.md). If the user says the review markdown was AI-authored, or authorship is unclear, do not treat it as the user's voice and do not use its phrasing to humanize the letter. Use it only as secondary factual notes, preferably after corroborating the detail with the resume, the original source, or explicit user-provided facts. If no performance-review material is available, write narrative evidence from the resume and job description rather than pasted bullet points, and avoid unsupported claims.

Use this evidence hierarchy:

1. Resume: factual boundary for roles, dates, technologies, and headline achievements.
2. Reliable human-authored performance reviews or original review sources: real project stories, working style, strengths, responsibilities, and impact.
3. Job description: employer priorities and language to respond to, not a source for claims about the user.

If a performance review supports a valuable detail that is not in the resume, use it conservatively and only when the text directly supports it. If the review markdown was AI-authored or synthesized, either corroborate the detail with another source or omit it. If a detail is ambiguous, omit it.

## Cover-Letter Shape

Write a polished English cover letter, usually 250-400 words, as a Markdown file. Aim for the upper half of the band (roughly 320-400 words) for senior technical roles that expect a concrete work story, and keep it on a single page.

Use this structure without headings:

1. Greeting to the company hiring team.
2. Specific opening naming the role and company.
3. One or two paragraphs that connect the job's highest-priority needs to the user's closest real experience, preferably as work stories grounded in performance-review evidence.
4. A short motivation paragraph explaining why this company or role is interesting, using only supported company/job facts. If no company facts are available, focus on the role's engineering impact rather than inventing mission language.
5. Brief closing and signature using the name from the resume.

## Human Voice Pass

Before saving the letter, revise it for applicant-specific human voice. This is an authenticity check, not a detector-bypass trick: the letter should read like a careful professional wrote from real evidence.

Remove or rewrite these common AI-writing tells:

- Generic polished claims with no lived detail, such as `results-driven professional`, `proven track record`, `dynamic`, `passionate`, `leveraged actionable insights`, or `translated data into actionable insights`.
- Default openings such as `I am excited to apply for...` unless the next sentence immediately makes it specific and grounded.
- Repetitive sentence structures, symmetrical paragraph lengths, and transition-heavy sequencing such as `Furthermore`, `Moreover`, `In addition`, or `In conclusion`.
- Flat, interchangeable praise of the employer, mission, culture, or innovation when the job description does not support the claim.
- Buzzword stacking that names many technologies without showing what the user actually did with them.
- Overly flawless corporate phrasing that removes the user's point of view, tradeoffs, constraints, or working context.

Prefer these humanizing moves:

- Open with a specific role/company connection or a concise summary of the user's closest matching work, not a generic enthusiasm sentence.
- Include one concrete work story with context, the user's action, and supported impact; a constraint, incident, migration, stakeholder need, or operational pressure often makes the story feel real.
- Use plain first-person professional language. Vary sentence length naturally, but keep the letter clean and readable.
- Keep one strong through-line instead of covering every requirement. The letter should sound selected and argued, not assembled from keywords.
- Use company/job details only when they were actually present in the inspected posting or company page.
- Do not borrow rhythm, phrasing, or polished narrative structure from AI-authored source notes; rewrite from the verified facts.

## Cover-Letter Rules

- Do not invent experience, skills, metrics, credentials, education, personal details, location, work authorization, or company facts.
- Do not repeat the resume as a list.
- Do not copy resume bullets verbatim or turn them into a paragraph with only cosmetic rephrasing.
- Do not overfit by naming every technology in the job description.
- Prefer concrete experience from performance reviews over generic enthusiasm or resume-bullet repetition.
- If the job asks for a technology the resume only supports adjacently, phrase it as adjacent strength, not direct ownership.
- Make the selected evidence feel valuable: include context, what the user did, why it mattered, and the impact only when supported.
- Keep tone professional, direct, and human; avoid clichés and excessive flattery.
- If the letter still feels generic after the human voice pass, do not save it yet; revise around a more specific supported example or a clearer role-company connection.

## Validation

Validate in two gates so a letter that fails the word band is never saved or uploaded:

1. Before saving — check the drafted letter mechanically against the word band (250-400 words) and the quality bar (single strong through-line, at least one concrete supported work story, no invented facts, human-voice pass done). Counting words may use a script; the quality read is your own. If it falls outside the band or still reads generic, revise and re-check; do not write the file until it passes.
2. After saving, before uploading or pasting — confirm a file exists at the exact path written to `cover_letter_path` and that the sheet cell reads back that intended path. Fix any mismatch before advancing the form.
