# Gmail and LinkedIn quirks

Behaviour of the mail data itself, not of any one agent's tools. Each of these
cost a real run to discover, and none are visible from a tool description.

## Gmail search

**`label:` can return an empty result for a label that exists.** Both the label
id (`label:Label_2888...`) and the display name (`label:"Apply!"`) have been
observed returning nothing while the label held 121 threads. The failure is
silent — indistinguishable from "no such mail" — so a `label:` query is unsafe
for any check whose answer you intend to act on.

Use `in:inbox` and `has:userlabels` instead. In particular express step 7's exit
check as `in:inbox has:userlabels`, never as a `label:` query: the whole point of
that check is to prove filed mail left the Inbox, and a query that silently
returns empty would "prove" it whether or not it was true.

## Reading LinkedIn mail

**LinkedIn messages are too large to read directly.** They run past 100 KB and
exceed the read limit, so the call fails and spills the body to a file. Do not
retry it — the second attempt fails the same way. Parse the saved file instead.

**A LinkedIn message states its own type in its tracking URLs**, and its visible
text often does not. A rejection's body may read only "Your update from
<company>", while the URLs around it contain `email_jobs_application_rejected_01`.
Search the raw HTML for `email_jobs_[a-z_0-9]+` and classify from that marker.

**LinkedIn bodies carry the posting id** as `/jobs/view/<digits>`. This is the
single strongest matching signal in the whole workflow — company and title both
collapse across rows, while a posting id is unique. Look it up as
`linkedin:<id>` in `by_url.json` from `pull_rows.py` for an exact row hit.

Beware the counterpart: a LinkedIn email may also contain *recommended* job
links. An id is decisive only when it is the sole posting link in the message, or
when it agrees with the company and title.

Pulling all three out of a spilled message file:

```bash
python -c "
import json, re, sys
d = json.load(open(sys.argv[1]))
h = d['htmlBody']
print('subject :', d['subject'])
print('type    :', set(re.findall(r'email_jobs_[a-z_0-9]+', h)) or 'not a LinkedIn template')
print('job ids :', set(re.findall(r'/jobs/view/(\d+)', h)))
" SAVED_FILE.txt
```

## Sender patterns

Application mail arrives from the ATS, not the employer, so the sending domain
rarely names the company: Teamtailor, Greenhouse, Ashby, Workable, Workday,
Personio, Lever, Rippling, SuccessFactors, HR-ON, Pinpoint, join.com and
Recruitee all appear. Take the company from the body, never from the domain.

The reverse also happens — a message whose sender *is* the company can be about a
role listed in the tracker under a recruiter or a LinkedIn page name. Two seen so
far: a Telnyx rejection matching a row filed under "Voice AI Space", and a 9fin
rejection matching a row filed under "Soapbox".
