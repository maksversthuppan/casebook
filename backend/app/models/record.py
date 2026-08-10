"""What happened to a Case over time.

Two records describe a date: the court's account of the listing, and the
advocate's own account of it. They are kept apart with one writer each, so that
a refresh has no reach into anything a person composed. See ADR-0002.
"""

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy import case as sa_case
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.case import Case
from app.models.enums import HearingSource, HearingState
from app.models.people import Advocate, Clerk


class Hearing(UUIDMixin, TimestampMixin, Base):
    """The record of a Case being listed on a date.

    Never edited by hand once the court has spoken: a court-sourced Hearing is
    the court's account, and changes only by applying a newer Snapshot.
    """

    __tablename__ = "hearings"
    __table_args__ = (
        # A case has one posting per date. Keeping this unique is what makes the
        # refresh takeover rule unambiguous - a Snapshot reporting on a date knows
        # exactly which Hearing it supersedes.
        UniqueConstraint("case_id", "date", name="uq_hearing_case_date"),
        # A Representation names exactly one firm member - never both at once.
        CheckConstraint(
            "NOT (represented_by_advocate_id IS NOT NULL "
            "AND represented_by_clerk_id IS NOT NULL)",
            name="ck_hearing_representation_one",
        ),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)

    state: Mapped[HearingState] = mapped_column(
        Enum(HearingState, name="hearing_state", native_enum=False, validate_strings=True),
        nullable=False,
        default=HearingState.scheduled,
    )
    source: Mapped[HearingSource] = mapped_column(
        Enum(HearingSource, name="hearing_source", native_enum=False, validate_strings=True),
        nullable=False,
        default=HearingSource.firm,
    )

    #: Why it was listed, in the court's words where we have them.
    purpose: Mapped[str | None] = mapped_column(String(300))
    #: What became of the date.
    outcome: Mapped[str | None] = mapped_column(Text)

    #: The portal says an order exists for this date. The file itself is phase 2;
    #: this is the signal that there is something to go and fetch.
    order_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Who noted it, when the firm recorded it. Null once the court owns it.
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )

    #: The judge or magistrate who sat on this Hearing. Court-sourced only, on
    #: the same footing as purpose and outcome - never entered by an advocate.
    presiding_officer: Mapped[str | None] = mapped_column(String(200))

    #: Which one firm member is on record for this Hearing - an Advocate or a
    #: Clerk, entered by a person, never by a refresh, settable before or after
    #: the date. Never both (see the check constraint below).
    represented_by_advocate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )
    represented_by_clerk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clerks.id", ondelete="SET NULL")
    )

    recorded_by: Mapped[Advocate | None] = relationship(
        lazy="joined", foreign_keys=[recorded_by_id]
    )
    represented_by_advocate: Mapped[Advocate | None] = relationship(
        lazy="joined", foreign_keys=[represented_by_advocate_id]
    )
    represented_by_clerk: Mapped[Clerk | None] = relationship(lazy="joined")


class DiaryEntry(UUIDMixin, TimestampMixin, Base):
    """What an advocate wrote about a Case on a date.

    Authored by a person, never by a refresh. This is the only content in the
    system that someone composed and could not get back, which is why the
    refresh boundary is drawn where it is.
    """

    __tablename__ = "diary_entries"
    __table_args__ = (
        # Full-text over the diary, for the single search box. Declared here as
        # well as in the migration so that metadata and database agree -
        # otherwise every later autogenerate helpfully proposes dropping it.
        # The expression must stay byte-for-byte what `app/api/search.py` emits,
        # or the index is built and never used.
        Index(
            "ix_diary_entries_body_fts",
            text("to_tsvector('english', body)"),
            postgresql_using="gin",
        ),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The date of record - the day being written about, not the day it was typed.
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advocates.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    author: Mapped[Advocate] = relationship(lazy="joined")


class InternalNote(UUIDMixin, TimestampMixin, Base):
    """Something recorded about a Case as a whole rather than about a date.

    Notes stay off the Timeline, because they are not about a day.
    """

    __tablename__ = "internal_notes"
    __table_args__ = (
        Index(
            "ix_internal_notes_body_fts",
            text("to_tsvector('english', body)"),
            postgresql_using="gin",
        ),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advocates.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    author: Mapped[Advocate] = relationship(lazy="joined")


class Task(UUIDMixin, TimestampMixin, Base):
    """Something an Advocate owes on a Case.

    A Task may record the Diary Entry it arose from, but it belongs to the Case,
    not to the entry - which is why `diary_entry_id` is `SET NULL` rather than
    `CASCADE`. Deleting the day's note must not take the obligation with it; the
    Task stays visible long after that day has scrolled out of the Timeline
    (CONTEXT.md, "Task").
    """

    __tablename__ = "tasks"
    __table_args__ = (
        # A deadline is one kind or the other, never both. Neither is also
        # allowed: plenty of work is owed without a date attached to it.
        CheckConstraint(
            "NOT (due_date IS NOT NULL AND due_before_next_hearing)",
            name="ck_task_one_kind_of_deadline",
        ),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)

    #: Who owes it. Required: a Task nobody owes is a note, and the system
    #: already has somewhere better to put those.
    assignee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advocates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )

    #: A fixed calendar date. Mutually exclusive with the flag below.
    due_date: Mapped[dt.date | None] = mapped_column(Date)
    #: The deadline most litigation actually has: expressed against the court's
    #: calendar, so when the court moves a date the deadline moves with it and
    #: nobody has to remember to edit anything (CONTEXT.md, "Due before the next
    #: hearing"). What it resolves to is read off the Hearings - see `due_on`.
    due_before_next_hearing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    #: Null until it is done. A timestamp rather than a boolean, because "when"
    #: is asked for as often as "whether", and who finished it is attribution
    #: the rest of the system already records.
    done_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    done_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )

    #: The Diary Entry this arose from, where it arose from one at all.
    diary_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("diary_entries.id", ondelete="SET NULL")
    )

    case: Mapped[Case] = relationship(lazy="joined")
    assignee: Mapped[Advocate] = relationship(lazy="joined", foreign_keys=[assignee_id])
    done_by: Mapped[Advocate | None] = relationship(lazy="joined", foreign_keys=[done_by_id])


# The Case's next hearing date is *read off* the Hearings, never stored, so it
# cannot drift from the timeline. Attached after Hearing exists because the two
# reference each other.
#
# Deliberately not filtered to future dates: a scheduled Hearing whose date has
# passed is exactly what an advocate needs to see, not something to hide.
Case.next_hearing_date = column_property(
    select(func.min(Hearing.date))
    .where(Hearing.case_id == Case.id, Hearing.state == HearingState.scheduled)
    .correlate_except(Hearing)
    .scalar_subquery(),
    deferred=False,
)

# What a Task's deadline actually falls on, resolved at read time rather than
# stored. A task due before the next hearing follows the court's calendar: move
# the date and the deadline moves with it, with nothing to remember to edit.
#
# Resolved in SQL rather than in Python so that "everything due this week"
# remains one ordered query - a task whose deadline is a moving target still
# sorts alongside one with a fixed date. Null means no deadline at all, and also
# means a case with no scheduled hearing to be due before yet.
Task.due_on = column_property(
    sa_case(
        (
            Task.due_before_next_hearing,
            select(func.min(Hearing.date))
            .where(Hearing.case_id == Task.case_id, Hearing.state == HearingState.scheduled)
            .correlate_except(Hearing)
            .scalar_subquery(),
        ),
        else_=Task.due_date,
    ),
    deferred=False,
)
