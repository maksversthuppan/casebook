# The Vakalath is the firm's own claim, not the court's

The portal names an advocate against each party it returns — including our own
client's side. So the system already holds an answer to "who is on record for us
in this Case", court-sourced, refreshed with everything else. Adding a Vakalath
field means holding a second answer to the same question, and a reader who
notices that will reasonably ask why we did not simply read the first.

Because they are not the same question. The portal reports what the **court's
file** currently says. The Vakalath records what the **firm** asserts. These
legitimately disagree, and the disagreement is the point:

- A vakalath filed on Tuesday is not on the portal on Tuesday. The firm knows it
  is on record before the court's own record says so.
- A vakalath returned may keep showing on the portal for weeks.
- The firm sometimes assists on a Case without being on record at all, under an
  outside advocate's vakalath. The portal names that advocate; the firm's own
  view of who holds the authority is the same name, and no Advocate row exists
  for them.
- The portal's spelling is the portal's — `ANIL KUMAR` against a registration
  number, not a link to a person. Treating it as identity is the silent matching
  ADR-0005 forbids everywhere else.

So the Vakalath is **entered by a person, never written by a Refresh** (rule 1,
ADR-0007), and deliberately **not reconciled** with the portal's answer. Where
the two differ, both are shown. That divergence is the only independent check
the firm has that a vakalath actually reached the file — collapsing them into
one field would destroy the signal in order to remove an apparent duplication.

It carries a holder and nothing else: either an Advocate of the firm or an
outside name in free text, never both, at most one per Case. It has no
lifecycle. Giving a Case up is a **Firm Status** of `relinquished`, decided
separately and for firm-side reasons — the two were considered as one act and
deliberately split, because a Case can be relinquished while the vakalath is
still on the file, and a vakalath can be returned on a Case the firm still holds
through another advocate.

Rejected: reading the holder off the portal and storing nothing of our own. It
is the smaller schema and it answers the wrong question — it tells the firm what
the court believes, which is exactly the thing the firm needs something to check
*against*.

Also rejected, for now: fixing the related contradiction underneath this. Our
own side's portal advocate is currently stored as a `Counsel` row, a term
`CONTEXT.md` reserves for the other side's lawyer. That is a real defect, it
predates this decision, and it is recorded in ROADMAP findings (2026-08-10) with
the three ways out. The Vakalath does not wait on it, and is unaffected by which
way it is eventually resolved — being, by this decision, a separate claim from
whatever the portal says.
