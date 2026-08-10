import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import HearingSource, HearingState
from app.schemas.people import AdvocateOut, ClerkOut


class HearingIn(BaseModel):
    """Recording a hearing the firm knows about - usually the next date, heard
    from the judge in open court.

    `source` is absent on purpose: anything created through the API is
    firm-recorded. Only a DCMS Snapshot produces a court-sourced Hearing.
    """

    model_config = ConfigDict(extra="forbid")

    date: dt.date
    state: HearingState = HearingState.scheduled
    purpose: str | None = Field(default=None, max_length=300)
    outcome: str | None = None


class HearingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date | None = None
    state: HearingState | None = None
    purpose: str | None = Field(default=None, max_length=300)
    outcome: str | None = None


class HearingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: dt.date
    state: HearingState
    source: HearingSource
    purpose: str | None
    outcome: str | None
    order_available: bool
    recorded_by: AdvocateOut | None
    #: Court-sourced only, same footing as purpose/outcome - never entered by
    #: an advocate.
    presiding_officer: str | None
    #: Who is on record as having represented the firm at this Hearing - an
    #: Advocate or a Clerk, never both. Firm-authored, never by a refresh.
    represented_by_advocate: AdvocateOut | None
    represented_by_clerk: ClerkOut | None


class RepresentationIn(BaseModel):
    """Setting or clearing a Hearing's Representation.

    Firm-authored data, unlike the rest of a court-sourced Hearing - settable
    regardless of the Hearing's source, and independently of the court-owned
    fields' edit lock (CONTEXT.md, "Representation").
    """

    model_config = ConfigDict(extra="forbid")

    advocate_id: uuid.UUID | None = None
    clerk_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def at_most_one(self) -> "RepresentationIn":
        if self.advocate_id is not None and self.clerk_id is not None:
            raise ValueError("a Representation names one firm member, not both")
        return self


class DiaryEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The day being written about, which is not always the day it is typed.
    date: dt.date
    body: str = Field(min_length=1)


class DiaryEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date | None = None
    body: str | None = Field(default=None, min_length=1)


class DiaryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: dt.date
    body: str
    author: AdvocateOut
    created_at: dt.datetime
    updated_at: dt.datetime


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    author: AdvocateOut
    created_at: dt.datetime
    updated_at: dt.datetime


class TaskIn(BaseModel):
    """Creating a Task.

    A deadline is a fixed date, or before the next hearing, or neither - never
    both at once (CONTEXT.md, "Due before the next hearing").
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    assignee_id: uuid.UUID
    due_date: dt.date | None = None
    due_before_next_hearing: bool = False
    #: The Diary Entry this arose from, where it arose from one. The Task is
    #: still the Case's, and outlives the entry.
    diary_entry_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_kind_of_deadline(self) -> "TaskIn":
        if self.due_date is not None and self.due_before_next_hearing:
            raise ValueError("a deadline is a fixed date or before the next hearing, not both")
        return self


class TaskUpdate(BaseModel):
    """`done` is the only field most edits touch, and it is deliberately not a
    plain boolean on the way out - see `TaskOut.done_at`."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    assignee_id: uuid.UUID | None = None
    due_date: dt.date | None = None
    due_before_next_hearing: bool | None = None
    done: bool | None = None

    @model_validator(mode="after")
    def one_kind_of_deadline(self) -> "TaskUpdate":
        if self.due_date is not None and self.due_before_next_hearing:
            raise ValueError("a deadline is a fixed date or before the next hearing, not both")
        return self


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    title: str
    assignee: AdvocateOut
    due_date: dt.date | None
    due_before_next_hearing: bool
    #: What the deadline actually falls on today, resolved from the Case's next
    #: scheduled Hearing where the deadline follows the court's calendar. Null
    #: means no deadline - or a Case with no date scheduled to be due before.
    due_on: dt.date | None
    done_at: dt.datetime | None
    done_by: AdvocateOut | None
    diary_entry_id: uuid.UUID | None
    created_at: dt.datetime


class TimelineHearing(BaseModel):
    kind: Literal["hearing"] = "hearing"
    date: dt.date
    hearing: HearingOut


class TimelineDiary(BaseModel):
    kind: Literal["diary"] = "diary"
    date: dt.date
    entry: DiaryEntryOut


TimelineItem = TimelineHearing | TimelineDiary
