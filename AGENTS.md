# Codex Wiki Agent

## Purpose

This workspace contains a Codex-maintained markdown wiki following the LLM-wiki pattern: raw sources are immutable, the wiki is the maintained knowledge layer, and this file is the schema that keeps future Codex sessions disciplined.

Use the wiki for accumulated knowledge that should outlive a chat thread: source summaries, entities, topics, recurring decisions, contradictions, query syntheses, and open questions.

## Workstation Skills

Three Codex skills support this wiki and are mirrored in `.codex/skills/`:

- `$wiki-read`: answer questions from the wiki with cited page links.
- `$wiki-maintain`: ingest sources, file durable answers, and update wiki pages.
- `$wiki-evolve`: lint, repair, and improve the wiki schema or structure.

## Directory Contract

- `raw/`: user-curated source material. Read from this directory, but do not edit, rename, delete, or reorganize files in it unless the user explicitly asks. Use `raw/assets/` for source images and attachments.
- `wiki/`: Codex-maintained markdown wiki. Codex may create and edit files here during wiki work.
- `wiki/index.md`: content-oriented catalog. Update this after every ingest, page creation, page rename, or substantial wiki edit.
- `wiki/log.md`: append-only chronological journal. Add one entry for every ingest, query filed to the wiki, lint pass, migration, or schema change.
- `wiki/sources/`: one page per raw source or external source.
- `wiki/entities/`: people, organizations, projects, systems, tools, places, and other named things.
- `wiki/topics/`: concepts, themes, processes, comparisons, and synthesized knowledge.
- `wiki/queries/`: durable answers or analyses that began as user questions.
- `wiki/meta/`: wiki health, schema notes, open questions, and maintenance plans.
- `wiki/templates/`: page templates. Use them as shape guidance, not rigid forms.

## Page Conventions

Use kebab-case filenames: `topic-name.md`, `person-or-project.md`, `source-title.md`.

Every normal wiki page should start with YAML frontmatter:

```yaml
---
title: "Readable Title"
type: source | entity | topic | query | meta
status: seed | active | needs-review | superseded
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources:
  - "wiki/sources/example.md"
tags:
  - example
---
```

Prefer concise sections with stable names:

- `## Summary`
- `## Key Points`
- `## Evidence`
- `## Links`
- `## Open Questions`

Use Obsidian-style wikilinks for wiki concepts and entities, for example `[[Applicant Tracking Systems]]`. Use markdown links for concrete file paths, raw files, and external URLs.

Do not present unsupported claims as settled facts. Factual claims should be traceable to a source page, a raw file, or a dated query entry. Mark weak claims with `needs-review`.

## Ingest Workflow

Default to ingesting one source at a time unless the user asks for a batch.

1. Identify the source in `raw/` or from the user-provided URL/text.
2. Read the source carefully. If it contains images or attachments, inspect them when they carry substantive information.
3. Create or update a page under `wiki/sources/` with a source summary, bibliographic metadata when available, key claims, and links to the raw file or URL.
4. Update or create affected topic/entity pages. Integrate the source into the existing synthesis instead of only appending a new summary.
5. Record contradictions, superseded claims, or uncertainty directly on the relevant pages.
6. Update `wiki/index.md`.
7. Append a `wiki/log.md` entry using:

```markdown
## [YYYY-MM-DD] ingest | Source or Batch Title
```

## Query Workflow

When answering from the wiki:

1. Read `wiki/index.md` first.
2. Use `rg` over `wiki/` to find relevant pages.
3. Read the most relevant pages before answering.
4. Cite wiki pages or source pages in the answer with markdown links.
5. Distinguish wiki-backed facts from inference.
6. If the answer is a useful synthesis, ask whether to file it, or file it directly when the user asks. Store filed answers in `wiki/queries/` or merge them into an existing topic page.

## Lint And Evolution Workflow

Periodic health checks should look for:

- Broken links and stale index entries.
- Orphan pages with no incoming links.
- Important concepts mentioned repeatedly but lacking pages.
- Duplicate or overlapping pages that should be merged.
- Contradictions between old and new claims.
- Pages with missing frontmatter or missing source provenance.
- Useful schema or workflow improvements.

Write durable audit results to `wiki/meta/health.md`, update `wiki/index.md` if page status changes, and append a `wiki/log.md` entry using:

```markdown
## [YYYY-MM-DD] lint | Scope
```

Schema changes are allowed when the user asks to evolve the wiki or when repeated maintenance work reveals a clear improvement. Keep schema edits small, update this file and relevant skill instructions together when needed, and log the change.

## Operating Rules

- Treat `raw/` as source of truth and `wiki/` as compiled knowledge.
- Preserve user-authored source files and existing application code.
- Prefer small, reviewable wiki edits over broad rewrites.
- Keep `wiki/log.md` append-only.
- Use `rg` for search and line-oriented checks.
- Never store secrets in the wiki. If raw sources contain private material, summarize only what is needed for the user's requested knowledge base.
