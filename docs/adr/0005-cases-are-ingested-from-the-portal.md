# Cases enter the system by being found on DCMS

A Case is normally created by searching for it on the portal: the advocate picks
the district and court, searches by whatever identifier they have — case number,
CNR or filing number — solves the CAPTCHA, and everything follows from the
result. **Ingestion is not a separate mechanism from Refresh.** It is the same
browser session, the same proxied CAPTCHA, the same parser and the same Snapshot
record, pointed at a Case that does not exist yet.

We had first planned for cases to be typed in by hand, with a Court learning its
portal district and establishment the first time somebody refreshed a case in it.
That was circular: the portal will not run any search until a court is chosen
(ADR-0004), so a Court could not be refreshed until it had those values, and the
values only arrived through a refresh. Beginning at the portal dissolves the
circularity — the Court is identified before the search rather than after it, and
is recorded from the portal's own dropdowns instead of being typed and hoped
about. The Case likewise arrives with its CINO already known, so nobody has to
copy a sixteen-character identifier off a court acknowledgement.

Three things the portal cannot tell us, so ingestion has to ask a person:
**which returned party is our client** — the portal knows petitioner and
respondent, not sides; **which of our advocates are on the case**, and in what
role; and the **Firm Status**. Party names also come back as free text, so each
is linked to an existing Party or creates one by an advocate's choice, never by
silent fuzzy matching. The portal's raw string is kept beside the link.

Creating a Case by hand remains, and is not a lesser path: a plaint filed this
morning has no registration number, no CINO and no portal record for days, and
the firm needs its diary from day one. Such a Case sits in a provisional Court
and cannot be refreshed until its Court is identified — which happens the first
time it is searched for.

The consequences we accept: a Case in a provisional Court is visibly not
refreshable until someone completes it; ingestion is more screens than a plain
form; and loading an existing backlog costs one CAPTCHA per case. The portal's
Advocate Name tab could later return many cases from one search, so the steps
that turn a parsed result into a Case are built to accept a list, even though
nothing feeds them one yet.
