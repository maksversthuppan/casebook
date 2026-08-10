"""Controlled vocabularies the firm owns.

Deliberately absent: Court Status. Its values belong to the portal, not to us, so
it is stored as free text and never coerced into an enum of our invention.
See CONTEXT.md, "Court Status".
"""

import enum


class FirmStatus(str, enum.Enum):
    """Whether the firm is working a Case. Independent of what the court says.

    `on_hold` and `relinquished` are different things and are never collapsed
    into one another: on hold is the firm's own pause on work it still holds and
    is still answerable for, relinquished is the firm having given the Case up
    (CONTEXT.md, "Firm Status"). `closed` is a third thing again - the work
    finished.
    """

    active = "active"
    on_hold = "on_hold"
    relinquished = "relinquished"
    closed = "closed"


class PartyRole(str, enum.Enum):
    """Which side a Party is on, in one Case. A Party may be a client in one and
    an opposite party in another."""

    client = "client"
    opposite_party = "opposite_party"


class AdvocateRole(str, enum.Enum):
    """An Advocate's standing involvement in a Case."""

    lead = "lead"
    assisting = "assisting"
    appearing = "appearing"


class RelationKind(str, enum.Enum):
    """How the Case holding the relation arose from the Case it points at:
    'AS/88/2025 is an appeal_of OS/412/2024'."""

    appeal_of = "appeal_of"
    execution_of = "execution_of"
    connected_to = "connected_to"


class PartyKind(str, enum.Enum):
    person = "person"
    organisation = "organisation"


class HearingState(str, enum.Enum):
    """A Hearing exists from the moment a date is announced, so most of its life
    is spent in `scheduled` - a date the firm is waiting for."""

    #: Announced, not yet reached. The earliest of these is the Case's next
    #: hearing date, which is always read off the Hearings and never stored.
    scheduled = "scheduled"
    #: The court has recorded what became of the date.
    held = "held"
    #: The date was changed before it was ever sat on.
    superseded = "superseded"
    #: The date passed and the court recorded nothing against it.
    unrecorded = "unrecorded"


class SearchMode(str, enum.Enum):
    """Which of the portal's search tabs was used.

    Refresh always uses `cnr` once a Case has its CINO. The others exist for
    Ingestion, where the advocate searches by whatever identifier they happen to
    have and the CINO is learned from the result.
    """

    cnr = "cnr"
    case_number = "case_number"
    filing_number = "filing_number"


class SnapshotStatus(str, enum.Enum):
    """A Snapshot is kept whatever becomes of it, including when an advocate
    rejects it as wrong - a broken parser should leave evidence, not vanish."""

    #: Fetched and stored, not yet acted on.
    captured = "captured"
    #: Taken as the Case's official position, as a whole.
    applied = "applied"
    #: An advocate judged it wrong and discarded it.
    rejected = "rejected"
    #: A later Snapshot was applied over it.
    superseded = "superseded"


class HearingSource(str, enum.Enum):
    """Where a Hearing came from.

    Advocates learn a date from the judge's own words in open court, days before
    the portal shows it and sometimes instead of the portal ever showing it
    reliably. A refresh takes over a firm-recorded Hearing for a date it reports
    on, and the court's version stands where the two disagree (ADR-0002).
    """

    firm = "firm"
    court = "court"
