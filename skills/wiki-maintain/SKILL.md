---
name: wiki-maintain
description: Maintain a local agent-managed markdown wiki by ingesting sources, creating source summaries, updating entity and topic pages, preserving provenance, recording contradictions, refreshing the index, and appending the log. Use when the user asks to process a raw source, add material to the wiki, update wiki pages, file an answer, or keep the wiki current.
---

# Wiki Maintain

## Overview

Integrate new information into the wiki as compiled knowledge. Do not merely summarize a source; update the pages that should become smarter because the source was read.

## Ingest Workflow

1. Find and read the nearest `AGENTS.md`; treat it as the wiki schema.
2. Identify the source path, URL, pasted text, or query answer to file.
3. Prefer one source per ingest unless the user requests a batch.
4. Read `wiki/index.md` and search `wiki/` with `rg` for related pages before writing.
5. Create or update a `wiki/sources/` page with summary, metadata, key claims, evidence, links, and open questions.
6. Update or create affected `wiki/entities/` and `wiki/topics/` pages. Integrate claims into the existing synthesis.
7. Mark contradictions, superseded claims, and uncertain claims where they belong.
8. Add Obsidian-style wikilinks for important wiki concepts and entities.
9. Update `wiki/index.md` with new or changed pages.
10. Append a `wiki/log.md` entry of type `ingest` (or the appropriate operation type), using the canonical log format defined in `AGENTS.md`.

## Source Rules

- Treat `raw/` as immutable. Read files there, but do not edit, rename, delete, or reorganize them unless explicitly asked.
- For external URLs, record the URL and access date on the source page. Browse only when current or precise source content is needed.
- If a source has substantive images, inspect them separately and record image-derived observations as such.
- Keep provenance close to the claims it supports.

## Page Quality

Every created or substantially changed page should have:

- Valid YAML frontmatter matching `AGENTS.md`.
- A short summary.
- Evidence or source links for factual claims.
- Related wikilinks when a concept or entity should connect to the graph.
- Open questions when the source leaves uncertainty.

## Editing Discipline

Prefer surgical edits over broad rewrites. Preserve useful prior synthesis, but revise it when newer evidence changes the conclusion. When a page becomes redundant, mark it `superseded` and link to the replacement before deleting anything.

## Final Check

Before finishing, verify changed wiki pages, `wiki/index.md`, and `wiki/log.md` are consistent. Tell the user what was ingested, which pages changed, and what gaps remain.
