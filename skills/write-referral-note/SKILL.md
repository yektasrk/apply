---
name: write-referral-note
description: Write the short note a contact submits when referring the user for a job, in the referrer's own voice, as an honest endorsement from someone who knows the user rather than a copy of the cover letter. Use when the user asks for a referral note, a referral message, an endorsement for a contact to send, or wants to apply to a job by referral.
---

# Write Referral Note

## Overview

A referral note is what the user's contact (the referrer) pastes into their company's referral form or sends to a recruiter. It must read like a real person vouching for someone they know: simple, warm, specific about *how the user works*, and honest about *how well the referrer knows them*. It is not a second cover letter.

When the user applies by referral, they usually want both documents. Write the cover letter first with the `submit-job-applications` cover-letter rules ([cover-letter-generation.md](../submit-job-applications/references/cover-letter-generation.md)), then write the note using this skill so the two can be compared.

## Inputs

Read these before drafting:

- The full job posting, for the role title and the team's priorities.
- [resume.md](../../resume.md) and the wiki [Job Application Form Defaults](../../wiki/topics/job-application-form-defaults.md) page for employers, what each employer does, the user's pronouns, and the current role.
- Performance reviews in `raw/performance-reviews/`, only to confirm that a working-style trait is real (see [performance-review-evidence.md](../submit-job-applications/references/performance-review-evidence.md)).
- The cover letter for this job, if one exists, so the note can be checked against it.
- **How the referrer knows the user.** Ask if the user hasn't said. Everything about the note's honesty depends on it.

## Honesty Rules (non-negotiable)

- **Never invent the relationship.** The note says how the referrer knows the user (for example "through a mutual friend", "from university", "we worked together at X"). Until the user tells you, leave a visible `[___]` placeholder and ask.
- **Match every claim to how close they are.** A former teammate can describe things they saw. Anyone else must not:
  - no "our cluster" or "when we worked together";
  - no scenes described as if the referrer saw them;
  - no "we've talked about work a lot" unless the user confirms it.

  A loose contact vouches from what they have heard, for example: "We haven't worked together, but from what I've heard about her work, I think she'd be a great fit."
- **Every trait must be true.** Each trait needs support in the resume or a reliable performance review. Company descriptions such as "largest" or "biggest" that come from general knowledge rather than the workspace must be pointed out to the user before they send the note.
- **Use the user's stated pronouns.** Take them from the wiki defaults page. If they are not recorded, ask; do not infer them from the name.

## What The Note Says

1. **Who and what:** a one-line referral for the named role.
2. **How the referrer knows the user**, then one sentence that sets how strong the endorsement is.
3. **Where the user has worked, and what those companies do:** name the employers and describe each in a few plain words, because a foreign recruiter may not recognise them. One sentence on what that experience means (for example, used to systems at real scale).
4. **Two or three working traits in general terms:**
   - Good: "takes security seriously and thinks about it from day one"; "likes everything done in code, so nothing gets set up by hand and every change gets reviewed"; "doesn't call something done just because it works, makes sure it's monitored, backed up and safe to run in production".
   - Bad: lists of tools or protocols (SSO, Kerberos, 2FA, Argo CD), metrics, cluster sizes, or project names. Those belong in the cover letter.
5. **One closing line of trust**, for example: "She's someone I'd trust with systems the whole company relies on."

## Voice And Style

- Write as a person talks: short, plain sentences in everyday words. Read it aloud; if it sounds like a job ad or a resume, simplify it.
- Write in flowing paragraphs. **Never use bullets or bold labels in the note itself**; mention the traits the way someone would in a message.
- Keep it to about 120–170 words, in two or three short paragraphs.
- Avoid buzzwords and hype (`results-driven`, `passionate`, `rockstar`, `leverage`). Mild warmth is fine; overselling makes a referral look coached.

## Keep It Separate From The Cover Letter

The note must not reuse the cover letter's wording, stories, or figures. A recruiter often reads both together, and repeated phrases make the note look ghost-written.

- Choose different material: the cover letter carries the technical story and the numbers; the note carries character, working habits, and the referrer's trust.
- Run the mechanical check. It must report no shared phrases before the note is handed over:

  ```bash
  python3 skills/write-referral-note/scripts/phrase_overlap.py "cover_letters/<Country>/<Company>.md" "cover_letters/<Country>/<Company>-referral-note.md"
  ```

  A role or team name the posting forces on both (for example "Data Platform team") may be reworded to clear the check, or left in if rewording would sound unnatural. Say which you chose.

The script is only a mechanical check. You write the prose yourself; no script or generator drafts or rewrites it.

## Offering Options

When the user is unsure what tone to use, give three or four short versions with clearly different angles: short and direct, warm and personal, work habits, plain recommendation. Add one line on when each fits, based on how close the referrer is to the user. Save them together in `<Company>-referral-note-options.md`, and copy the chosen one into the final note file.

## Where To Save

- Final note: `cover_letters/<Country>/<Company>-referral-note.md`, next to the cover letter. It is plain prose with no heading, so it can be pasted straight into a form.
- Options, when drafted: `cover_letters/<Country>/<Company>-referral-note-options.md`.
- Revise these files freely during the session. Never overwrite a note from an earlier session; add a numeric suffix (`<Company>-2-referral-note.md`), the same rule as for cover letters.
- The note is personal candidate data. `cover_letters/` is Git-ignored; never commit it.

## Finishing

1. Run the phrase-overlap check and confirm it reports no shared phrases.
2. Confirm that nothing in the note overstates the relationship, and that every trait has support.
3. Send the user the Markdown file. Point out anything left to fill in (`[___]`) and any claim that comes from general knowledge.
4. If the job has a sheet row, the note is not recorded in it. Only `cover_letter_path` exists, so say that no path was recorded.
