---
name: wiki-evolve
description: Audit, repair, and evolve a local agent-maintained markdown wiki. Use when the user asks for a wiki health check, lint pass, broken-link scan, orphan detection, contradiction review, taxonomy cleanup, schema improvement, migration, or recommendations for making the wiki more useful over time.
---

# Wiki Evolve

## Overview

Improve the wiki as a system: structure, consistency, provenance, links, schema, and maintainability.

## Audit Workflow

1. Read the nearest `AGENTS.md`, `wiki/index.md`, `wiki/log.md`, and `wiki/meta/health.md`.
2. Use `rg` and file listings to inspect `wiki/` for structural drift.
3. Check index coverage against actual pages.
4. Check frontmatter presence and page type consistency.
5. Check links, backlinks, orphans, duplicate topics, stale status values, and missing provenance.
6. Look for recurring concepts that deserve pages.
7. Look for contradictions or superseded claims, especially where newer sources conflict with older synthesis.
8. Write findings and completed repairs to `wiki/meta/health.md`.
9. Update `wiki/index.md` when statuses, page summaries, or page locations change.
10. Append a `wiki/log.md` entry of type `lint` or `schema`, using the canonical log format defined in `AGENTS.md`.

## Checks To Run

- `wiki/index.md` lists every durable page with an accurate one-line summary.
- Every non-template wiki page has frontmatter with all fields required by the schema in `AGENTS.md`.
- Source-backed claims link to source pages or raw files.
- Pages with many outgoing references have useful incoming links.
- No important page is isolated unless it is intentionally standalone.
- Similar pages are linked, merged, or clearly distinguished.
- `needs-review` and `superseded` pages have next actions.
- Log headings follow the canonical log format defined in `AGENTS.md`.

## Repair Rules

Make low-risk repairs directly when the user's request allows maintenance:

- Fix stale index entries.
- Add missing backlinks and related links.
- Add missing frontmatter fields when values are obvious.
- Add provenance notes where the cited source is clear.
- Mark uncertain pages as `needs-review`.

For high-impact changes, summarize the intended migration before editing:

- Renaming many pages.
- Merging or deleting pages.
- Changing the schema in `AGENTS.md`.
- Reorganizing major directory categories.

## Evolution Rules

Evolve the schema only when it reduces repeated maintenance cost or improves retrieval quality. Keep changes small, backward-compatible when possible, and reflected in `AGENTS.md`, templates, and any affected skills.

End with a short report: repairs made, unresolved findings, recommended next sources or questions, and whether any schema changes were applied.
