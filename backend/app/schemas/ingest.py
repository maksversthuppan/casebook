import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import FirmStatus, SearchMode
from app.schemas.case import AssignmentIn
from app.schemas.people import PartyIn


class StartOut(BaseModel):
    session_id: str
    #: Straight from the portal's own dropdown, not from anything we maintain.
    districts: list[str]


class ChooseDistrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    district: str


class ChooseDistrictOut(BaseModel):
    courts: list[str]


class ChooseCourtIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    court: str


class ChooseCourtOut(BaseModel):
    """What the portal said was chosen, verbatim.

    These three strings are what get recorded onto the Court. They must match the
    portal's own wording exactly or a later refresh cannot re-select it.
    """

    state: str
    district: str
    court: str
    case_types: list[str]
    #: Set when the firm already has this establishment as a complete Court.
    known_court_id: uuid.UUID | None = None
    known_court_name: str | None = None


class IdentifierIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: SearchMode
    value: str = Field(min_length=1, max_length=100)
    #: Only for the Case No and Filing No tabs; CNR asks for neither.
    case_type: str | None = None
    year: str | None = None

    @model_validator(mode="after")
    def _case_type_and_year_required_unless_cnr(self) -> "IdentifierIn":
        if self.mode is not SearchMode.cnr:
            if not self.case_type or not self.case_type.strip():
                raise ValueError("Case type is required for this search")
            if not self.year or not self.year.strip():
                raise ValueError("Year is required for this search")
        return self


class CaptchaOut(BaseModel):
    """The CAPTCHA as an inline data: URI, to be shown to a person.

    Read from the page and passed through untouched. Never interpreted.
    """

    captcha: str
    #: Set when a Case with this CINO already exists. Warned about before the
    #: advocate spends a CAPTCHA on it.
    duplicate_case_id: uuid.UUID | None = None


class SubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    captcha: str = Field(min_length=1, max_length=20)


class PortalPartyOut(BaseModel):
    """One side of a case, in the portal's own vocabulary - see `PortalParty`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    advocate_name: str | None
    advocate_registration: str | None


class PortalCaseOut(BaseModel):
    """What `extract_case` read out of a Snapshot, for the review screen to show.

    Read-only: nothing here is editable, because none of it is ours to change
    (ADR-0002) - the review screen only asks what the portal cannot know.
    """

    model_config = ConfigDict(from_attributes=True)

    cino: str
    case_type: str | None
    registration_number: str | None
    registration_date: date | None
    filing_number: str | None
    filing_date: date | None
    court_status: str | None
    subject: str | None
    petitioner: PortalPartyOut | None
    respondent: PortalPartyOut | None
    #: Individuals the lead name's "and N Others"/"and ANOTHER" stands in for -
    #: real people the portal enumerates separately, previously read by
    #: nothing here at all. Each needs its own review, same as the lead party.
    petitioner_others: list[PortalPartyOut] = []
    respondent_others: list[PortalPartyOut] = []
    first_hearing: date | None
    next_hearing: date | None
    last_hearing: date | None


class SubmitOut(BaseModel):
    """The result of one search, already stored.

    The Snapshot is written before any of this is worked out, so a parse failure
    leaves evidence rather than nothing.
    """

    snapshot_id: uuid.UUID
    raw_length: int
    raw_preview: str
    parsed: dict | None
    parse_error: str | None
    #: What was read out of `parsed`, or `None` if the search found no case -
    #: the review screen has nothing to review in that case.
    extracted: PortalCaseOut | None = None
    duplicate_case_id: uuid.UUID | None = None


class ReviewPartyIn(BaseModel):
    """Either an existing Party by id, or a new one to create - same shape as
    `CasePartyIn` minus `role`, which the review screen derives from
    `ReviewIn.client_side` instead of asking twice."""

    party_id: uuid.UUID | None = None
    new_party: PartyIn | None = None

    @model_validator(mode="after")
    def one_or_the_other(self) -> "ReviewPartyIn":
        if (self.party_id is None) == (self.new_party is None):
            raise ValueError("give exactly one of party_id or new_party")
        return self


class ReviewIn(BaseModel):
    """What the portal cannot know about a found Case (ADR-0005): which
    returned party is ours, which Advocate holds which role, and Firm Status.

    `petitioner` / `respondent` are required exactly when the Snapshot's
    `extracted` carried that side - checked against the Snapshot at the
    endpoint, since a schema alone cannot see what was actually returned.
    `petitioner_others` / `respondent_others` are checked the same way, one
    per individual `extracted.petitioner_others`/`respondent_others` reported
    - every one of them is linked or created by a person, never silently
    matched (ADR-0005), same as the lead party.
    """

    model_config = ConfigDict(extra="forbid")

    client_side: Literal["petitioner", "respondent"]
    petitioner: ReviewPartyIn | None = None
    respondent: ReviewPartyIn | None = None
    petitioner_others: list[ReviewPartyIn] = Field(default_factory=list)
    respondent_others: list[ReviewPartyIn] = Field(default_factory=list)
    assignments: list[AssignmentIn] = Field(min_length=1)
    firm_status: FirmStatus = FirmStatus.active
