"""What a Refresh would do to a Case, laid out for a person to decide on.

Everything here is a *description* of the one plan `app/services/refresh.py`
builds. The screen and the apply step read the same plan, so "apply all" can
only ever do what was shown - which is the whole point of showing it, given
that a Snapshot is applied whole or not at all (rule 2, ADR-0007).
"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import HearingSource, HearingState, SnapshotStatus


class FieldChangeOut(BaseModel):
    """One court-sourced field the Snapshot would change.

    `before` and `after` are already rendered as text: a diff screen compares
    values, and the moment a date or a status is typed it is being read, not
    computed with.
    """

    field: str
    label: str
    before: str | None
    after: str | None


class HearingFaceOut(BaseModel):
    """A Hearing as it reads on one side of the change."""

    model_config = ConfigDict(from_attributes=True)

    state: HearingState
    source: HearingSource
    purpose: str | None
    outcome: str | None
    presiding_officer: str | None
    order_available: bool


class HearingChangeOut(BaseModel):
    """One date the Snapshot has something to say about.

    `change` is `new` for a date the Case has no Hearing on at all, `changed`
    where one exists and the court's account differs, and `superseded` for the
    other direction - a date the court used to report as still coming and no
    longer mentions (ADR-0007).
    """

    date: date
    change: Literal["new", "changed", "superseded"]
    #: True when the firm recorded this date itself and the court's account is
    #: about to stand over it (ADR-0002). Worth saying out loud on the screen.
    takes_over_firm_record: bool
    before: HearingFaceOut | None
    after: HearingFaceOut


class ListChangeOut(BaseModel):
    """A block replaced wholesale - Act & Section, or one party's Counsel."""

    label: str
    before: list[str]
    after: list[str]


class RefreshDiffOut(BaseModel):
    """The whole of what applying this Snapshot would do.

    `has_changes` false is a real and common answer: nothing at the court has
    moved since the last look. The Snapshot is still kept, and applying it
    still records that the Case was confirmed today (CONTEXT.md, "Last
    Refreshed").
    """

    snapshot_id: uuid.UUID
    case_id: uuid.UUID
    status: SnapshotStatus
    fetched_at: datetime

    #: False when the portal matched nothing at all. Then there is nothing to
    #: apply, only a Snapshot to keep and a search to think again about.
    found: bool
    #: What the portal answered about. A Refresh searches by CINO, so anything
    #: other than the Case's own is an answer about a different case and is
    #: refused rather than applied.
    cino: str | None = None
    cino_mismatch: bool = False
    parse_error: str | None = None
    #: Shown when there is nothing else to show - a person paid a CAPTCHA and
    #: is owed sight of what came back.
    raw_preview: str = ""

    fields: list[FieldChangeOut] = []
    hearings: list[HearingChangeOut] = []
    act_sections: ListChangeOut | None = None
    crime_details: list[FieldChangeOut] = []
    counsel: list[ListChangeOut] = []

    #: Names the portal reports that no Party on this Case is linked to. A
    #: Refresh never links or creates one - that is a person's judgement
    #: (ADR-0005) - so these are reported and left.
    unlinked_parties: list[str] = []
    #: Dates the firm has on record as still coming that the court says nothing
    #: about. Left exactly alone; this disagreement is why ADR-0002 keeps
    #: firm-recorded and court-reported apart in the first place.
    firm_dates_not_reported: list[date] = []

    has_changes: bool = False


class RefreshStartOut(BaseModel):
    """A refresh session, opened and driven as far as the CAPTCHA.

    The advocate chooses nothing: the Court is already identified and the CINO
    is already known, so the portal is walked to the CAPTCHA in one call and
    the only thing left for a person is the thing only a person may do.
    """

    session_id: str
    captcha: str
    cino: str
    state: str
    district: str
    court: str


class SnapshotSummaryOut(BaseModel):
    """One Snapshot in a Case's refresh history.

    Every Snapshot ever taken for the Case, applied or not - an advocate paid a
    CAPTCHA for each of them (rule 3).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: SnapshotStatus
    fetched_at: datetime
    decided_at: datetime | None
    search_mode: str
    search_value: str
    parse_error: str | None
