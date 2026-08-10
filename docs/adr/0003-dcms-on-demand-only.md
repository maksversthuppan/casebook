# This repository is the source of truth; DCMS is consulted on demand

The Kerala DCMS portal is treated as an outside reference, not as a database to
mirror. Almost everything of value to the firm — diary entries, documents, notes,
tasks, party records — exists only here and has no counterpart on the portal.
What DCMS contributes is the official account of hearings and status, pulled one
Case at a time when an advocate presses **Refresh from DCMS**.

There is deliberately no scheduled synchronisation and no background scraping.
The portal's search is gated by a CAPTCHA that refreshes every thirty seconds,
and **the CAPTCHA is always solved by the advocate.** We make no attempt to
bypass, automate or defeat it, or any other protection on the portal. Automating
it would be the only way to sync on a schedule, so on-demand refresh is not a
first-phase compromise — it is the design.

This keeps our traffic to the portal proportionate to real use and keeps the firm
working when the portal is slow, changed or down, which for a five-advocate
practice matters more than freshness. The cost is that a case's official data is
only as current as the last time someone asked for it, so nothing in the system
may assume court data is up to date — status and hearing dates carry the time
they were last refreshed, and reminders are driven by what the firm knows rather
than by what the portal might be showing now.
