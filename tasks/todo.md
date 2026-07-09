# Skill improvements — 2026-07-09

Plan approved by user: apply review findings 1–8 in one pass, 9–10 as a separate pass.

## Pass 1 — corrections and precision (items 1–8)

- [x] 1. Remove stale `me_applyed` column reference (submit SKILL.md)
- [x] 2. Remove dead `job-apply-agent` path (triage SKILL.md)
- [x] 3. Un-hardcode `Asia/Tehran` timezone; defer to current-sheet.md (submit SKILL.md)
- [x] 4. Name `service_account.json`, `job_finder/sheets.py`, `job_finder/config.py` explicitly (triage SKILL.md)
- [x] 5. Trim frontmatter descriptions of both job skills to trigger-focused 2–3 sentences
- [x] 6. Define default batch sizes (triage: 5–10 rows; submit: 5 rows per run)
- [x] 7. Add mechanical validation step to triage workflow (word count, file exists, cell round-trip)
- [x] 8. Document legacy `Yes`/`No` status values consistently in both job skills

## Pass 2 — structural (items 9–10)

- [x] 9. Wiki skills: defer log/frontmatter formats to AGENTS.md; added canonical log format to AGENTS.md
- [x] 10. Job skills: repo-relative paths; sheet `cover_letter_path` still stores absolute paths resolved at runtime

## Pass 3 — review gate and ask-on-blocker (2026-07-10, user request via skill-creator)

- [x] Default changed from "submit when complete" to review-before-submit: new `## Review Gate` section; workflow steps 10–11, Overview, description, and browser-form-flow.md form loop updated; ambiguous buttons treated as final.
- [x] Unknown required fields no longer abandon the row: new `## Unknown-Field Blockers` section (fill everything else, keep form open, ask the user, then return to the review gate; save durable answers to wiki form defaults); safety rule, workflow step 12, and browser-form-flow.md blocker/field-handling sections updated.
- [x] Success-seeking mode now targets "filled and awaiting review", one application at a time; reporting adds awaiting-review / awaiting-answer counts.
- [x] Codex `agents/openai.yaml` short_description/default_prompt aligned.

## Live test (2026-07-10)

- [x] Triage skill: Denmark rows 89-93 processed end-to-end; 1 Suitable + letter (369 words, validated), 4 Not Suitable with specific reasons; all writes verified by readback. New validation step (item 7) exercised successfully.
- [x] Submit skill: full pass on row 89 (Relesys) after the user installed the Chrome extension. Verified: company-site route preferred over The Hub middleman, cookie declines, all fields filled, review gate stopped at Submit, unknown-blocker flow asked the user (CV upload restricted by extension → user dragged it in; location-field wording corrected per user), user approved, submitted with confirmation, applied_at + notes written. User preference saved to wiki defaults + lessons.md.

## Review

- 7 tracked files changed (AGENTS.md, all 5 SKILL.md files, browser-form-flow.md); ~28 insertions / 27 deletions — surgical, no restructuring.
- Appended a `schema`-type entry to `wiki/log.md` (gitignored, on disk) per AGENTS.md rules for schema changes.
- Verified: `rg` finds no remaining `me_applyed`, `job-apply-agent`, or `/Users/yekta` absolute paths under `skills/`; both `.claude/skills/` and `.codex/skills/` symlink mirrors intact (edits propagate automatically); both trimmed descriptions re-registered correctly in the live skill index.
- Not committed — awaiting user review.
