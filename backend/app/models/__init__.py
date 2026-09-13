"""All models, imported here so Alembic autogenerate and the metadata see them."""

from app.models.base import Base
from app.models.case import (
    ActSection,
    Assignment,
    Case,
    CaseParty,
    CaseRelation,
    CaseTag,
    Counsel,
    CrimeDetail,
    FirmStatusChange,
    Tag,
)
from app.models.case_type import CaseType
from app.models.court import Court
from app.models.dcms import DcmsSnapshot
from app.models.enums import (
    AdvocateRole,
    FirmStatus,
    HearingSource,
    HearingState,
    PartyKind,
    PartyRole,
    RelationKind,
    SearchMode,
    SnapshotStatus,
)
from app.models.people import Advocate, Clerk, Party

# Imported last: it attaches Case.next_hearing_date, which needs both Case and
# Hearing to exist.
from app.models.record import DiaryEntry, Hearing, InternalNote, Task  # noqa: E402

__all__ = [
    "ActSection",
    "AdvocateRole",
    "Advocate",
    "Assignment",
    "Base",
    "Case",
    "CaseParty",
    "CaseRelation",
    "CaseTag",
    "CaseType",
    "Clerk",
    "Counsel",
    "Court",
    "CrimeDetail",
    "DcmsSnapshot",
    "DiaryEntry",
    "FirmStatus",
    "FirmStatusChange",
    "SearchMode",
    "SnapshotStatus",
    "Hearing",
    "HearingSource",
    "HearingState",
    "InternalNote",
    "Party",
    "PartyKind",
    "PartyRole",
    "RelationKind",
    "Tag",
    "Task",
]
