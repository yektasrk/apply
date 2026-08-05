# Wiki Agent

## Purpose

This workspace contains an agent-maintained markdown wiki following the LLM-wiki pattern: raw sources are immutable, the wiki is the maintained knowledge layer, and this file is the schema that keeps future agent sessions disciplined. The rules here apply to whichever agent is running (Codex, Claude, or another tool).

Use the wiki for accumulated knowledge that should outlive a chat thread: source summaries, entities, topics, recurring decisions, contradictions, query syntheses, and open questions.

## Workstation Skills

Skills live canonically in `skills/` and are mirrored into `.codex/skills/` and `.claude/skills/` via `setup-agent-skills.sh`. Three maintain this wiki:

- `wiki-read`: answer questions from the wiki with cited page links.
- `wiki-maintain`: ingest sources, file durable answers, and update wiki pages.
- `wiki-evolve`: lint, repair, and improve the wiki schema or structure.

Four more run the job-application pipeline over the Google Sheets described in `README.md`. They are not wiki skills, but they read wiki knowledge for answer defaults and one writes back into `wiki/queries/`:

- `triage-job-applications`: mark sheet rows `Suitable` / `Not Suitable` with a sheet-visible reason.
- `submit-job-applications`: fill applications, write cover letters into `cover_letters/`, and record outcomes after a review gate.
- `gmail-job-application-reconcile`: classify application email and sync defensible outcomes to the sheet.
- `report-job-market`: aggregate triaged rows into `wiki/queries/job-market-fit-report.md`.

Each skill carries its own operational procedure. This file is the schema those procedures defer to: the directory contract, page conventions, and log format below.

## Directory Contract

- `raw/`: user-curated source material. Read from this directory, but do not edit, rename, delete, or reorganize files in it unless the user explicitly asks. Use `raw/assets/` for source images and attachments.
- `wiki/`: agent-maintained markdown wiki. The agent may create and edit files here during wiki work.
- `wiki/index.md`: content-oriented catalog. Update this after every ingest, page creation, page rename, or substantial wiki edit.
- `wiki/log.md`: append-only chronological journal. Add one entry for every ingest, query filed to the wiki, lint pass, migration, or schema change. Every entry heading follows `## [YYYY-MM-DD] <type> | <Title>`, where `<type>` is one of `ingest`, `query`, `lint`, `schema`, `migration`, or `setup`. This is the canonical log format; skills reference it rather than redefining it.
- `wiki/sources/`: one page per raw source or external source.
- `wiki/entities/`: people, organizations, projects, systems, tools, places, and other named things.
- `wiki/topics/`: concepts, themes, processes, comparisons, and synthesized knowledge.
- `wiki/queries/`: durable answers or analyses that began as user questions.
- `wiki/meta/`: wiki health, schema notes, open questions, and maintenance plans.
- `wiki/templates/`: page templates. Use them as shape guidance, not rigid forms.
- `wiki/README.md`: wiki overview page. Keep it aligned with this schema when the schema changes.
- `cover_letters/`: agent-generated application material, filed as `<Country>/<Company>.md`. Never overwrite an existing letter.
- `tasks/`: local-only session scratch for plans and working notes. Durable lessons do not belong here — put them in this file, the relevant skill, or the wiki.

`raw/`, `wiki/`, `cover_letters/`, and `tasks/` are Git-ignored because they hold personal candidate data or session scratch. Never commit their contents.

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

## Workflow Invariants

`wiki-maintain`, `wiki-read`, and `wiki-evolve` carry the step-by-step procedures. These invariants hold whether or not a skill is loaded:

- **Read before writing.** Start from `wiki/index.md` and `rg` over `wiki/` to find related pages. Never create a page that duplicates one already there.
- **Integrate, do not append.** A new source is merged into the existing synthesis on topic and entity pages, not bolted on as a second summary.
- **Record conflict where it lives.** Contradictions, superseded claims, and uncertainty go on the affected page, not only in the log.
- **Every write updates the index.** `wiki/index.md` must still describe the wiki after any ingest, page creation, rename, or substantial edit.
- **Every operation appends one log entry**, in the canonical format:

```markdown
## [YYYY-MM-DD] ingest | Source or Batch Title
## [YYYY-MM-DD] lint | Scope
```

- **Answers cite their pages.** Cite wiki or source pages with markdown links, and distinguish wiki-backed fact from inference. File a durable answer in `wiki/queries/` or merge it into an existing topic page.
- **Audits are durable.** Health-check results go to `wiki/meta/health.md`, not just the chat.

Default to ingesting one source at a time unless the user asks for a batch. When a source carries images or attachments, inspect them when they hold substantive information.

Schema changes are allowed when the user asks to evolve the wiki, or when repeated maintenance reveals a clear improvement. Keep them small, update this file and the affected skills together, and log the change.

## Operating Rules

- Treat `raw/` as source of truth and `wiki/` as compiled knowledge.
- Preserve user-authored source files and existing application code.
- Prefer small, reviewable wiki edits over broad rewrites.
- Keep `wiki/log.md` append-only.
- Use `rg` for search and line-oriented checks.
- Never store secrets in the wiki. If raw sources contain private material, summarize only what is needed for the user's requested knowledge base.
