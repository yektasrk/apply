# Agent Guide (Claude)

This workspace is tool-agnostic: it works with both Claude and Codex. The complete
working contract — wiki schema, directory rules, page conventions, and every
workflow — lives in `AGENTS.md`, which is imported below so there is a single
source of truth. Keep durable, tool-neutral rules in `AGENTS.md`; keep only
Claude-specific notes here.

@AGENTS.md

## Claude-specific notes

- Claude discovers project skills in `.claude/skills/`. This repo keeps the
  canonical, tool-neutral skills in `skills/` and mirrors them into both
  `.codex/skills/` and `.claude/skills/`, so **`skills/` is the single source
  of truth** — edit skills there and both tools stay in sync. The available
  skills are: `wiki-read`, `wiki-maintain`, `wiki-evolve`,
  `triage-job-applications`, `submit-job-applications`, and
  `report-job-market`.
- **One-time setup:** run `bash setup-agent-skills.sh` from the repo root to
  create both per-tool mirrors (symlinks into `skills/`, with a copy fallback
  for filesystems without symlink support). Re-run it after adding a new skill
  under `skills/`.
- The `agents/openai.yaml` file inside some skills is Codex-only interface
  metadata; Claude ignores it.
- `AGENTS.md` and the skills are written tool-neutrally ("the agent", "you") —
  every rule applies equally to Claude. If any stray "Codex" wording remains,
  read it as "the agent".
- Codex invokes a skill with `$skill-name`. With Claude, describe the task in
  natural language (e.g. "answer this from the wiki with citations") and the
  matching skill's description triggers it, or invoke it by name directly.
