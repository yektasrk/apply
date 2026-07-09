---
name: wiki-read
description: Read and answer from a local agent-maintained markdown wiki. Use when the user asks questions about accumulated wiki knowledge, wants cited answers from wiki pages, asks to inspect the wiki, or asks whether the wiki already contains information about a source, entity, topic, or previous query.
---

# Wiki Read

## Overview

Answer from the maintained markdown wiki without modifying it by default. Treat the wiki as compiled knowledge and raw sources as provenance.

## Workflow

1. Find the nearest `AGENTS.md` from the current workspace and follow its wiki schema.
2. Read `wiki/index.md` first to orient on available pages.
3. Search with `rg` across `wiki/` for the user's topic, aliases, and related terms.
4. Read the most relevant source, entity, topic, query, and meta pages.
5. Read raw files only when the wiki page provenance is missing, ambiguous, or challenged by the user.
6. Answer with citations to wiki pages or source pages using markdown links.
7. Separate wiki-backed facts from inference. Call out missing evidence or stale pages.
8. Do not edit files unless the user asks to file the answer or update the wiki.

## Answer Shape

Prefer concise answers with:

- A direct answer first.
- Short supporting bullets when the topic is complex.
- Local citations such as `[Topic](wiki/topics/example.md)` or `[Source](wiki/sources/example.md)`.
- A brief "Gaps" note if the wiki lacks enough evidence.

## Filing Answers

If the answer creates durable synthesis, ask whether to file it unless the user explicitly requested a wiki update. When filing:

- Store a new durable answer in `wiki/queries/` or merge it into the most relevant `wiki/topics/` page.
- Update `wiki/index.md`.
- Append a `wiki/log.md` entry of type `query`, using the canonical log format defined in `AGENTS.md`.
