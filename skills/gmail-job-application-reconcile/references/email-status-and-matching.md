# Email status and matching reference

Use this reference after reading full Gmail bodies. These are conservative heuristics, not substitutes for message-specific evidence.

## Status phrases

### Resume Reject

Require language such as:

- “will not be progressing” or “will not be moving forward”
- “decided not to progress”
- “unable to move forward with your application”
- “we have decided to move forward with other candidates”
- “we regret to inform you” or “we have declined your application”
- LinkedIn application-rejection templates whose body or tracking marker explicitly identifies rejection

Do not classify a message as rejection merely because it says the application is under review, the company received many applications, or the role is closed.

### Online Meeting

Require an actual invitation or scheduling action, for example:

- “we would like to invite you to an interview”
- “please choose a time” or “book a time for a call”
- “schedule your interview”
- a calendar/meeting invitation with a proposed interview or screening call

Do not classify these as `Online Meeting`:

- “if you progress to the next stage, you’ll have a call”
- “we will contact you if selected”
- a general interview-process guide
- “we may schedule a video interview within 1–2 weeks”

### Resume Send

Use for explicit acknowledgements such as:

- “your application was sent”
- “we received your application”
- “thank you for applying” when the message clearly refers to a submitted application
- “your application was submitted successfully”

Candidate-account activation, verification, or profile-setup messages are relevant to filing but are not sufficient by themselves for a `Resume Send` cell update.

## Matching rules

1. Extract the role title and company from the message body before relying on the subject. ATS emails often put the useful role wording only in the body.
2. Normalize case, punctuation, HTML entities such as `&amp;`, dashes, and repeated whitespace.
3. Score evidence in this order:
   - exact job URL and matching title/company;
   - exact company plus exact role title;
   - unique exact company match;
   - unique title plus sender/company context.
4. LinkedIn mail can contain multiple job links, including recommendations. A URL is strong evidence only when it is the sole relevant listing link or also agrees with title/company.
5. For duplicate rows, use location and existing application state. Do not guess between UK/Ireland/Netherlands copies of the same role.
6. Preserve an existing value when the email is older, generic, or ambiguous. A later explicit outcome is allowed to replace an earlier `Resume Send`.

## Default tracker context

The tracker used for this workflow is the existing Google Sheet titled `Jobs!` with spreadsheet ID `1lfYlHw_W9YzkFfE6IQZEnHTbORHBjAZ-p2-3F_AyKKQ`. Reconfirm metadata before use because tabs, rows, and labels can change. Its user filing label is exactly `Apply!`, not `Apply` or `apply`.
