# Performance Review Evidence

## Purpose

Performance reviews can be a useful evidence source for cover-letter stories when they are human-authored or otherwise reliable because they may describe work the user actually did, strengths observed over time, collaboration style, scope, and impact. If the local markdown was AI-authored or synthesized, do not treat it as the user's voice and do not use it as prose to imitate. Use it only as secondary factual notes, and prefer facts also supported by the resume, original review source, or explicit user confirmation.

## Importing Google Docs

When the user provides Google Docs performance reviews:

1. Use the Google Drive/Docs connector to read each source document.
2. Convert each document to markdown and save it in the project under `raw/performance-reviews/`.
3. Use kebab-case filenames with a stable identifier, such as `2025-h1-performance-review.md` or `yektanet-2026-review.md`.
4. Include basic provenance at the top of each markdown file: source title, Google Doc URL or ID, import date, and whether the content is complete or partial.
5. Do not edit the imported meaning. Preserve factual content and mark any unclear extraction as `needs-review`.

Creating or updating these markdown files is mechanical source ingestion. It does not allow scripts or tools to generate suitability reasoning, rejection reasons, or cover-letter prose.

## Using The Evidence

Before drafting a cover letter, read the relevant performance-review markdown alongside the resume and full job description only if it is relevant and reliable enough for the task. Extract only details that are directly supported by the review text, and if the markdown was AI-authored, corroborate important details before using them.

Prefer evidence that shows:

- ownership of a real project or operational responsibility
- measurable or clearly described impact
- reliability, automation, security, platform, or incident-response strengths
- collaboration across teams or influence without authority
- technical judgment under production constraints
- repeated feedback themes, not one-off praise

Avoid:

- unsupported claims, inflated scope, or invented metrics
- copying review sentences verbatim unless a short phrase is necessary
- copying or imitating AI-authored review phrasing, rhythm, or narrative structure
- using private feedback that would be awkward or inappropriate in a job application
- turning every positive point into the letter; select only the strongest match for the job

If no performance-review evidence is available for a job's strongest priority, either use resume-supported evidence conservatively or omit that angle.
