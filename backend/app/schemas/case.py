import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AdvocateRole, FirmStatus, PartyRole, RelationKind
from app.schemas.court import CourtOut
from app.schemas.people import AdvocateOut, PartyIn, PartyOut


class CasePartyIn(BaseModel):
    """Either an existing Party by id, or a new one to create."""

    party_id: uuid.UUID | None = None
    new_party: PartyIn | None = None
    role: PartyRole
    position: int = 1

    @model_validator(mode="after")
    def one_or_the_other(self) -> "CasePartyIn":
        if (self.party_id is None) == (self.new_party is None):
            raise ValueError("give exactly one of party_id or new_party")
        return self


class CounselOut(BaseModel):
    """The other side's lawyer, as the portal names them - never a system user."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    registration: str | None


class CasePartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: PartyRole
    position: int
    portal_raw_name: str | None
    party: PartyOut
    counsels: list[CounselOut]


class AssignmentIn(BaseModel):
    advocate_id: uuid.UUID
    role: AdvocateRole


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: AdvocateRole
    advocate: AdvocateOut


class CaseCreate(BaseModel):
    """Manual case creation - the filing-day path.

    Requires only a court, one client and one advocate. A plaint filed this
    morning has no registration number and no CINO for days, and must still be
    able to hold a diary from day one.
    """

    court_id: uuid.UUID | None = None
    new_court_name: str | None = Field(default=None, max_length=300)

    parties: list[CasePartyIn] = Field(min_length=1)
    assignments: list[AssignmentIn] = Field(min_length=1)

    cino: str | None = Field(default=None, max_length=32)
    filing_number: str | None = None
    filing_date: date | None = None
    registration_number: str | None = None
    registration_date: date | None = None
    case_type: str | None = None
    firm_status: FirmStatus = FirmStatus.active
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def court_given_once(self) -> "CaseCreate":
        if (self.court_id is None) == (self.new_court_name is None):
            raise ValueError("give exactly one of court_id or new_court_name")
        return self

    @model_validator(mode="after")
    def needs_a_client(self) -> "CaseCreate":
        if not any(p.role is PartyRole.client for p in self.parties):
            raise ValueError("a case needs at least one client")
        return self


class CaseUpdate(BaseModel):
    """Only what the firm owns.

    Court Status, CINO and the hearing record are absent by design: those are the
    court's account, changed by applying a DCMS Snapshot and never by hand
    (ADR-0002).

    extra="forbid" so an attempt to set one of them is refused outright rather
    than silently dropped - a caller trying to write court data should hear about
    it, not appear to succeed.
    """

    model_config = ConfigDict(extra="forbid")

    firm_status: FirmStatus | None = None
    #: Why the Firm Status changed. Recorded on the Firm Status History entry,
    #: never on the Case itself - it describes the change, not the Case. Ignored
    #: when the status is unchanged, there being no entry to hang it on.
    firm_status_reason: str | None = None
    filing_number: str | None = None
    filing_date: date | None = None
    registration_number: str | None = None
    registration_date: date | None = None
    case_type: str | None = None
    tags: list[str] | None = None


class VakalathIn(BaseModel):
    """Setting or clearing a Case's Vakalath.

    Exactly one holder or neither: an Advocate of the firm, or an outside name
    the firm is assisting under. Giving neither clears it, which is how a Case
    goes back to having no Vakalath recorded (ADR-0008).
    """

    model_config = ConfigDict(extra="forbid")

    advocate_id: uuid.UUID | None = None
    holder_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def at_most_one(self) -> "VakalathIn":
        if self.advocate_id is not None and self.holder_name:
            raise ValueError("a vakalath names one holder: an advocate or a name, not both")
        return self


class FirmStatusChangeOut(BaseModel):
    """One entry of the Firm Status History.

    `created_at` is when the change was made - the entry is written at the moment
    it happens and never edited, so there is no second timestamp worth having.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: FirmStatus | None
    to_status: FirmStatus
    reason: str | None
    changed_by: AdvocateOut | None
    created_at: datetime


class CaseRelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: RelationKind
    note: str | None
    related_case_id: uuid.UUID


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class CrimeDetailOut(BaseModel):
    """The police case a Case relates to. Present only where the court records
    one - most Cases have none (ADR-0006)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cr_no: str | None
    fir_no: str | None
    fir_year: int | None
    fir_date: date | None
    investigating_officer: str | None
    police_station: str | None
    rank: str | None


class ActSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    act_code: str | None
    act_name: str
    section: str | None


class CaseSummary(BaseModel):
    """The case-list row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cino: str | None
    registration_number: str | None
    filing_number: str | None
    case_type: str | None
    court: CourtOut
    court_status: str | None
    firm_status: FirmStatus
    last_refreshed_at: datetime | None
    #: Read off the Hearings - the earliest one still scheduled - and never
    #: stored, so it cannot disagree with the timeline. May be in the past, which
    #: means a date passed with no outcome recorded and wants attention.
    next_hearing_date: date | None
    parties: list[CasePartyOut]
    assignments: list[AssignmentOut]


class CaseDetail(CaseSummary):
    tags: list[TagOut]
    created_at: datetime
    updated_at: datetime
    crime_details: CrimeDetailOut | None
    act_sections: list[ActSectionOut]
    #: The Vakalath: one of these at most, and often neither. An Advocate of the
    #: firm, or an outside name the firm assists under. The firm's own claim -
    #: not the advocate the portal names for our side, which is a separate thing
    #: and may legitimately disagree (ADR-0008).
    vakalath_advocate: AdvocateOut | None
    vakalath_holder_name: str | None
