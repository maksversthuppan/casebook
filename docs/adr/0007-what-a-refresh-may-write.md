# A Refresh replaces every court-sourced fact, and touches nothing else

Rule 1 has read "a refresh may write Hearings and Court Status, and nothing
else" since ADR-0002. That was written when a Snapshot carried nothing else
worth writing. It now carries Act & Section, Crime Details, Counsel, a
presiding officer per Hearing, and the court's own registration and filing
labels — every one of them the court's account, and none of them anything a
person composed.

So the rule is restated by what it protects rather than by a list of two
fields: **a Refresh replaces every court-sourced fact on a Case, wholesale, and
never touches anything a person entered.** The half of ADR-0002 that matters is
unchanged — the destructive half of a refresh still has no reach into authored
content.

A Refresh writes:

- **Court Status**
- **Registration number and date, filing number and date, case type** —
  court-issued labels that legitimately change over a Case's life. A plaint
  filed in March is registered in June, and learning that registration number
  without anyone retyping it is a large part of what Refresh is for.
- **Hearings** on every date the Snapshot reports on, taking over a
  firm-recorded Hearing for the same date and standing where the two disagree
  (ADR-0002) — purpose, outcome, presiding officer, whether an order is
  available.
- **Act & Section**, replaced wholesale (ADR-0006).
- **Crime Details**, replaced wholesale, and removed if the court has stopped
  reporting one.
- **Counsel** against each `CaseParty` it can match, replaced wholesale.

A Refresh never writes:

- a **Diary Entry**, an **Internal Note**, a **Task**, or a **tag** — authored
  content, the only content in the system nobody can get back.
- **Firm Status** — the firm's own view, which legitimately disagrees with the
  court's.
- **which Party a `CaseParty` points at**, or its role. A Snapshot naming
  somebody the firm has not linked is reported on the diff screen and left for
  a person to link, never matched by text (ADR-0005).
- a Hearing's **Representation** — firm-authored, and deliberately outside the
  court's account of a date.
- **CINO** — a Refresh searches *by* it. A response carrying a different one is
  refused outright rather than applied, because it is an answer about a
  different case.
- a **Hearing on a date the Snapshot says nothing about**, with one exception: a
  *court-sourced* Hearing still `scheduled` on a date the Snapshot no longer
  reports becomes `superseded`, which is exactly what that state is for. A
  *firm-recorded* scheduled date the court does not mention is left alone and
  surfaced on the diff screen — that disagreement is the reason ADR-0002 split
  firm-recorded from court-reported in the first place.

The thin Snapshot is the case that would quietly do damage. One whose follow-up
burst never arrived — an older capture, or a portal that answered with the
search row alone — must not be read as "the court reports no acts and no crime
details" and wipe them. Each block is replaced only when the Snapshot actually
carried a response of that shape, which is why the parser records which shapes
it saw rather than only what it found in them.

Rejected: per-field selection on the diff screen. It reads as the helpful
option, and it is the one thing rule 2 forbids — a Case holding half a Snapshot
makes every later comparison meaningless, because nothing afterwards can say
which half came from where. Apply the whole thing, or discard it and keep the
Snapshot as evidence.
