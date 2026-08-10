# Case Repository

The firm's own record of every proceeding it acts in. It holds the working
knowledge — diary, notes, tasks, and in time documents — and treats the Kerala
DCMS portal as an outside reference consulted on demand, never as the record
itself.

## Language

### The Case

**Case**:
One proceeding before one court. A Case is the thing advocates open, work in and
refresh; everything else in the system hangs off it. A Case usually enters the
system by Ingestion, but it need not: one may exist from the moment the firm
takes the work on, before the court has given it any number at all.
_Avoid_: matter, file, suit, brief — each implies a grouping above the Case, and
no such grouping exists.

**Case Relation**:
A directional link from one Case to another recording how the second proceeding
arose from the first — an appeal, an execution, a connected proceeding. Cases
stay independent records; the relation only lets an advocate walk between them.
_Avoid_: parent case, child case, case group.

**CINO**:
The permanent statewide identifier the court assigns to a Case, unique across
Kerala and unchanged for the life of the proceeding. A Case may exist before it
has one: a Case created on filing day is found on the portal by its case number
or filing number instead, and that first search is how it learns its CINO. Every
Refresh afterwards goes by CINO.
_Avoid_: CNR, case id — the portal shows the same value under other names, but
CINO is the term used here.

**Filing Number** / **Registration Number**:
Two different court-issued labels for the same Case: the first given when the
papers are presented, the second when the court formally registers it. Both are
labels, never identity — a Case keeps working when neither is known yet.
_Avoid_: case number — too ambiguous to use on its own, since it means the
registration number in conversation and the filing number on filing day.

**Court Status**:
Where the court says a Case stands — pending, disposed, and the portal's other
values. Reported by DCMS, displayed as the court's word, and never edited here.

**Firm Status**:
Whether the firm is working a Case: active, on hold, relinquished, or closed.
Set by advocates and independent of the Court Status — a disposed Case under
appeal is active work, and a Case pending for years with an unresponsive client
is not. Every list and dashboard in the app filters on this, not on Court Status.

**On hold** and **relinquished** are different things and must never be
collapsed into one another. On hold is the firm's own pause on work it
still holds — the client has gone quiet, the fee is unsettled — and the firm
remains answerable for the Case. Relinquished means the firm has given the Case
up; it is shown prominently wherever the Case appears, because an advocate who
does not know that is at risk of acting on a Case that is no longer theirs.
Closed is a third thing again: the work finished.
_Avoid_: current status, case status — both invite confusion with the court's
view. Always say which of the two is meant. Never call a relinquished Case one
that is on hold.

**Firm Status History**:
Every change of Firm Status a Case has been through — what it was, what it
became, which Advocate decided, when, and why if they said. Kept because a Case
reading "relinquished" today invites exactly one question, and the answer should
not depend on someone remembering. Deliberately not part of the Timeline: the
Timeline is what the court and the advocates did about the Case, and this is the
firm's own bookkeeping about it.
_Avoid_: audit log, status log — nothing else in the system is audited, and
naming it so implies a general facility that does not exist.

**Crime Details**:
The police case a Case relates to — FIR number and date, CR number, police
station, investigating officer and rank. Present only where the court records
one; most Cases have none; a Case never gains this by anything other than a
Refresh. Reported by DCMS, displayed as the court's word, and never edited
here — the same footing as Court Status.
_Avoid_: FIR, crime — "Crime Details" is the portal's own heading, and it names
a police case the court associates with this proceeding, not a criminal charge
in the abstract.

**Act & Section**:
One law and section a Case is brought under, as the portal pairs them. A Case
carries a list of these — several is normal, not an edge case — replaced
wholesale by every Ingestion and Refresh, the same as any other court-sourced
fact (rule 2: never merged one at a time).
_Avoid_: charge, statute — the portal's own act/section pairing is kept
together rather than split into two separate ideas.

### People

**Advocate**:
A member of the firm who uses the system. Every Diary Entry, Firm Status change
and applied Snapshot is attributed to one.
_Avoid_: user, lawyer, counsel — the other side's lawyer is **Counsel**, a
different and unrelated term, never a user here.

**Clerk**:
A member of the firm recorded by name but who does not use the system — no
login of their own. Named by an Advocate wherever the firm needs to say who is
responsible for something without that being the Advocate who appeared in
court.
_Avoid_: staff, assistant.

**Assignment**:
An Advocate's standing involvement in a Case, held as a role — **lead**,
**assisting**, or **appearing**. A Case may have several. Any Case where an
Advocate holds a role is one of their own cases, so nobody loses sight of work
they are doing but do not lead. Who actually represented the firm at a given
Hearing is that Hearing's **Representation**, not the Assignment — the
Assignment is standing across the whole Case, never tied to one date. Fuller
narrative about what happened that day still belongs on a Diary Entry.
_Avoid_: assigned advocate, owner — both imply exactly one.

**Vakalath**:
The authority to appear in a Case, and the one name it stands in. A Case either
has one or it has none; where it has one, that name is either an Advocate of the
firm or somebody outside it recorded in words — the firm sometimes assists on a
Case without being on record itself. Entered by a person and never by a Refresh,
even though the portal names an advocate for our own side as well: the two are
separate claims about the same fact, and where they disagree that is worth
seeing rather than reconciling silently.
_Avoid_: vakalatnama — that is the document; the Vakalath here is the standing
authority, not the paper. Also avoid treating the name on the Vakalath as the
lead Advocate: an Assignment's lead and the Vakalath's name are often the same
person and need not be.

**Party**:
A person or organisation the firm has dealt with, recorded once and reused
across every Case it appears in. A Party exists independently of any Case — and
so does what the firm knows about them: a phone number, an address, a standing
note such as "speaks only Malayalam" or "her son handles everything". Anything
true of one Case only is an Internal Note on that Case, never a note on the
Party.
_Avoid_: contact, person, litigant.

**Client** / **Opposite Party**:
Roles a Party holds in a particular Case, not separate kinds of thing. The same
Party may be a Client in one Case and an Opposite Party in another.
_Avoid_: petitioner, respondent, plaintiff, defendant — those are court-specific
labels that vary by case type; role is the firm's own view of which side a Party
is on.

**Counsel**:
The other side's lawyer, as the portal names them against a `CaseParty`. Never
a system user and never conflated with Advocate. A `CaseParty` may carry
several — this case's respondent has two on record at once — so Counsel is a
list, not a single name.
_Avoid_: advocate, opposing advocate — Advocate is reserved for firm members
who use the system; Counsel never does.

**Court**:
A single court establishment before which Cases proceed. Every DCMS search
begins by choosing a district and a court, so a Court must be named exactly as
the portal names it before any Case there can be searched at all. The firm
records only the courts it actually appears in.
_Avoid_: bench, forum, court complex — a complex contains several
establishments, and it is the establishment that matters here.

A Court is **provisional** while it is only a name somebody typed, and
**complete** once it has been identified against the portal's own district and
court lists — which happens the first time a Case there is ingested. Only a
complete Court can be searched, so a Case in a provisional Court cannot be
refreshed until someone identifies its Court.

### What happens over time

**Hearing**:
The record of a Case being listed on a date — why it was listed and what became
of it. A Hearing exists from the moment a date is announced, so a date the firm
is waiting for is as real a record as one already past.
_Avoid_: proceeding, business, sitting, posting — the portal uses several of
these for the same record.

Every Hearing says where it came from. **Firm-recorded** means an advocate noted
it, usually from the judge's own words in court, which is how the firm learns a
date days before the portal shows it. **Court-reported** means DCMS has spoken
about that date. A refresh takes over a firm-recorded Hearing for the same date,
and where the two disagree the court's version stands.

A Hearing is in one of four states:
- **Scheduled** — announced, not yet reached. The earliest of these is the Case's
  next hearing date, which is always read off the Hearings and never kept
  separately.
- **Held** — the court has recorded what became of the date.
- **Superseded** — the date was changed before it was ever sat on.
- **Unrecorded** — the date passed and the court recorded nothing against it.

**Presiding Officer**:
The judge or magistrate who sat on a Hearing. Court-sourced only, on the same
footing as a Hearing's purpose and outcome — never entered by an advocate, and
absent until the court reports one.
_Avoid_: officer alone — this Case's own Crime Details carries an
*investigating* officer, and its proceedings text may separately name a
*Protection* Officer under the Act it is brought under. All three are
different people; "Presiding Officer" is never ambiguous between them.

**Representation**:
Which one firm member — an Advocate or a Clerk — is on record for a Hearing.
Ordinarily the Advocate who actually appeared, entered after the fact; it may
also be set in advance, before the date, as who is expected to. A Clerk is
recorded instead when the point is only knowing who to ask, not which Advocate
stood up. Distinct from an Assignment, which is the Case's standing roster
rather than one Hearing's.
_Avoid_: assigned advocate, representative — "assigned advocate" collides with
Assignment's own avoided terms for the same reason: it implies exactly one
person across the whole Case rather than one per Hearing.

**Diary Entry**:
What an advocate writes about a Case on a date: what happened, what the client
was told, what must happen next. Authored by a person, never by a refresh, and
possible on any date whether or not the Case was listed.
_Avoid_: note, daily proceedings, log entry.

**Internal Note**:
Something recorded about a Case as a whole rather than about a date — the
client's instructions, a strategy, a warning for whoever picks the file up.
Notes do not appear on the Timeline, because they are not about a day.
_Avoid_: comment, remark. If it is about what happened on a date, it is a Diary
Entry.

**Timeline**:
The single chronological view of a Case that interleaves its Hearings and its
Diary Entries. A reading order, not a record of its own — nothing is stored
against the Timeline itself.
_Avoid_: history, case history — the portal uses "case history" for its own
list of Hearings alone.

**Task**:
Something an Advocate owes on a Case. A Task may record the Diary Entry it arose
from, but it is the Case's, not the entry's, so it stays visible long after that
day has scrolled out of the Timeline.
_Avoid_: to-do, follow-up, reminder — a reminder is a notification about a Task,
not the Task itself.

**Due before the next hearing**:
A deadline expressed against the court's calendar rather than a fixed date. It
resolves to whatever the Case's next scheduled Hearing is at the time of asking,
so when the court moves a date the deadline moves with it and no one has to
remember to edit anything. Most litigation deadlines are of this kind.
_Avoid_: relative due date, dynamic deadline.

### The portal

**Ingestion**:
Bringing a Case into the system by finding it on DCMS: choose the district and
court, search by whatever identifier the firm happens to have, and take the
result as the Case's first Snapshot. This is the ordinary way a Case comes into
existence, and it is the same act as a Refresh — only into a Case that does not
exist yet. It is also how a Court becomes complete, since the search cannot begin
without identifying one.
_Avoid_: import, onboarding — and do not use it for a Case someone types in by
hand, which is a different thing.

**Refresh**:
A single deliberate act by an advocate: fetch what DCMS currently says about one
Case that already exists here. Never scheduled, never done in bulk, and never
completed without a person reading the CAPTCHA.
_Avoid_: sync, poll, scrape — all three imply something automatic and recurring,
which this is not.

**DCMS Snapshot**:
What the portal said about one Case at one moment, recorded exactly as received
and never altered afterwards. A Snapshot is kept whether or not it is applied to
the Case, including when an advocate rejects it as wrong.
_Avoid_: response, payload, fetch result.

**Applying a Snapshot**:
Taking a Snapshot's contents to be the Case's official position, as a whole. A
Snapshot is applied entirely or not at all — a Case never holds a mixture of
portal data and human correction, so that every later comparison means something.
The Snapshot taken at Ingestion is applied as a matter of course, there being
nothing yet to compare it against.
_Avoid_: merge, sync, accept changes.

**Last Refreshed**:
When a Case's official data was last confirmed against DCMS. Because refreshing
is something a person chooses to do, every piece of court-sourced data on a Case
is only as current as this moment, and is shown with it. A Case nobody has
refreshed in a long time is **stale** — not wrong, but unconfirmed, and worth
surfacing to whoever holds it.
_Avoid_: last synced, up to date.
