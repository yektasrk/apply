#!/usr/bin/env bash
#
# setup-agent-skills.sh
#
# Mirror the canonical, tool-neutral skills in skills/ into the per-tool
# discovery directories so this repo works with both Codex and Claude:
#
#   skills/<name>  ->  .codex/skills/<name>   (Codex discovery)
#   skills/<name>  ->  .claude/skills/<name>  (Claude discovery)
#
# skills/ is the single source of truth — edit skills there only.
#
# Usage: bash setup-agent-skills.sh   (run from the repo root)
#
# It prefers symlinks (zero drift). If the filesystem does not support
# symlinks, it falls back to copying the skill folder.

set -euo pipefail
cd "$(dirname "$0")"

SKILLS=(
  wiki-read
  wiki-maintain
  wiki-evolve
  triage-job-applications
  submit-job-applications
)

TOOL_DIRS=(
  .codex/skills
  .claude/skills
)

if [ ! -d skills ]; then
  echo "error: skills/ not found. Run this from the repo root." >&2
  exit 1
fi

for dir in "${TOOL_DIRS[@]}"; do
  mkdir -p "$dir"

  for s in "${SKILLS[@]}"; do
    src="skills/$s"
    link="$dir/$s"

    if [ ! -d "$src" ]; then
      echo "skip    $s (missing under skills/)"
      continue
    fi

    # Remove any previous mirror so re-runs are clean.
    rm -rf "$link"

    if ln -s "../../skills/$s" "$link" 2>/dev/null && [ -f "$link/SKILL.md" ]; then
      echo "linked  $link -> ../../skills/$s"
    else
      # Fallback: copy for filesystems without symlink support.
      rm -rf "$link"
      cp -R "$src" "$link"
      echo "copied  $src -> $link"
    fi
  done
done

echo "Done. .codex/skills and .claude/skills now mirror skills/."
