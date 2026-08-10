"""Hearings, diary entries, internal notes, and the Timeline that merges the
first two.

The guards in here are the point of the module. See ADR-0002.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentAdvocate, Db
from app.models import (
    Advocate,
    Case,
    Clerk,
    DiaryEntry,
    Hearing,
    HearingSource,
    InternalNote,
    Task,
)
from app.schemas.record import (
    DiaryEntryIn,
    DiaryEntryOut,
    DiaryEntryUpdate,
    HearingIn,
    HearingOut,
    HearingUpdate,
    NoteIn,
    NoteOut,
    RepresentationIn,
    TaskIn,
    TaskOut,
    TaskUpdate,
    TimelineDiary,
    TimelineHearing,
    TimelineItem,
)

router = APIRouter(prefix="/cases/{case_id}", tags=["record"])


async def _case_or_404(db: Db, case_id: uuid.UUID) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


# --------------------------------------------------------------------------
# Hearings
# --------------------------------------------------------------------------


@router.get("/hearings", response_model=list[HearingOut])
async def list_hearings(case_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> list[Hearing]:
    result = await db.execute(
        select(Hearing).where(Hearing.case_id == case_id).order_by(Hearing.date)
    )
    return list(result.unique().scalars())


@router.post("/hearings", response_model=HearingOut, status_code=status.HTTP_201_CREATED)
async def record_hearing(
    case_id: uuid.UUID, payload: HearingIn, db: Db, advocate: CurrentAdvocate
) -> Hearing:
    """Records a hearing the firm knows about.

    Always firm-sourced. The advocate hears "post to 6 November" in open court
    and knows it that afternoon, days before the portal shows it - which is what
    lets the dashboard work with no DCMS integration at all.
    """
    await _case_or_404(db, case_id)

    hearing = Hearing(
        case_id=case_id,
        date=payload.date,
        state=payload.state,
        purpose=payload.purpose,
        outcome=payload.outcome,
        source=HearingSource.firm,
        recorded_by_id=advocate.id,
    )
    db.add(hearing)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This case already has a hearing on {payload.date.isoformat()}",
        ) from exc
    return hearing


@router.patch("/hearings/{hearing_id}", response_model=HearingOut)
async def amend_hearing(
    case_id: uuid.UUID,
    hearing_id: uuid.UUID,
    payload: HearingUpdate,
    db: Db,
    _: CurrentAdvocate,
) -> Hearing:
    hearing = await db.get(Hearing, hearing_id)
    if hearing is None or hearing.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hearing not found")

    # Once the court has spoken about a date, its account stands. Correcting it
    # by hand would put the Case somewhere between the portal and our own
    # guesswork, and the next comparison would mean nothing.
    if hearing.source is HearingSource.court:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This hearing came from DCMS and cannot be edited by hand. "
            "Refresh the case to take a newer version from the court.",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(hearing, field, value)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This case already has a hearing on that date"
        ) from exc
    return hearing


@router.delete("/hearings/{hearing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_hearing(
    case_id: uuid.UUID, hearing_id: uuid.UUID, db: Db, _: CurrentAdvocate
) -> None:
    hearing = await db.get(Hearing, hearing_id)
    if hearing is None or hearing.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hearing not found")
    if hearing.source is HearingSource.court:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A hearing reported by DCMS cannot be deleted by hand"
        )
    await db.delete(hearing)
    await db.commit()


@router.put("/hearings/{hearing_id}/representation", response_model=HearingOut)
async def set_representation(
    case_id: uuid.UUID,
    hearing_id: uuid.UUID,
    payload: RepresentationIn,
    db: Db,
    _: CurrentAdvocate,
) -> Hearing:
    """Who is on record as having represented the firm at this Hearing.

    Firm-authored, unlike the rest of a court-sourced Hearing - settable
    regardless of `hearing.source`, because a Representation is not part of
    the court's account (CONTEXT.md, "Representation"). Give neither id to
    clear it.
    """
    hearing = await db.get(Hearing, hearing_id)
    if hearing is None or hearing.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hearing not found")

    if payload.advocate_id is not None:
        if await db.get(Advocate, payload.advocate_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Advocate not found")
    if payload.clerk_id is not None:
        if await db.get(Clerk, payload.clerk_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Clerk not found")

    hearing.represented_by_advocate_id = payload.advocate_id
    hearing.represented_by_clerk_id = payload.clerk_id
    await db.commit()
    # The FK ids just changed; the joined-loaded relationships have not.
    await db.refresh(hearing, attribute_names=["represented_by_advocate", "represented_by_clerk"])
    return hearing


# --------------------------------------------------------------------------
# Diary entries
# --------------------------------------------------------------------------


@router.get("/diary", response_model=list[DiaryEntryOut])
async def list_diary(case_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> list[DiaryEntry]:
    result = await db.execute(
        select(DiaryEntry)
        .where(DiaryEntry.case_id == case_id)
        .order_by(DiaryEntry.date.desc(), DiaryEntry.created_at.desc())
    )
    return list(result.unique().scalars())


@router.post("/diary", response_model=DiaryEntryOut, status_code=status.HTTP_201_CREATED)
async def write_diary_entry(
    case_id: uuid.UUID, payload: DiaryEntryIn, db: Db, advocate: CurrentAdvocate
) -> DiaryEntry:
    await _case_or_404(db, case_id)
    entry = DiaryEntry(
        case_id=case_id, date=payload.date, body=payload.body, author_id=advocate.id
    )
    db.add(entry)
    await db.commit()
    return entry


async def _own_entry_or_error(
    db: Db, case_id: uuid.UUID, entry_id: uuid.UUID, advocate: Advocate
) -> DiaryEntry:
    entry = await db.get(DiaryEntry, entry_id)
    if entry is None or entry.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diary entry not found")
    # Not a permission in the RBAC sense - everyone in the firm reads everything.
    # It is that a diary entry is one person's account of a day, and editing it
    # under someone else's name would misattribute it.
    if entry.author_id != advocate.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "A diary entry can only be changed by whoever wrote it",
        )
    return entry


@router.patch("/diary/{entry_id}", response_model=DiaryEntryOut)
async def amend_diary_entry(
    case_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: DiaryEntryUpdate,
    db: Db,
    advocate: CurrentAdvocate,
) -> DiaryEntry:
    entry = await _own_entry_or_error(db, case_id, entry_id, advocate)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.commit()
    return entry


@router.delete("/diary/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_diary_entry(
    case_id: uuid.UUID, entry_id: uuid.UUID, db: Db, advocate: CurrentAdvocate
) -> None:
    entry = await _own_entry_or_error(db, case_id, entry_id, advocate)
    await db.delete(entry)
    await db.commit()


# --------------------------------------------------------------------------
# Internal notes
# --------------------------------------------------------------------------


@router.get("/notes", response_model=list[NoteOut])
async def list_notes(case_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> list[InternalNote]:
    result = await db.execute(
        select(InternalNote)
        .where(InternalNote.case_id == case_id)
        .order_by(InternalNote.created_at.desc())
    )
    return list(result.unique().scalars())


@router.post("/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def add_note(
    case_id: uuid.UUID, payload: NoteIn, db: Db, advocate: CurrentAdvocate
) -> InternalNote:
    await _case_or_404(db, case_id)
    note = InternalNote(case_id=case_id, body=payload.body, author_id=advocate.id)
    db.add(note)
    await db.commit()
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_note(
    case_id: uuid.UUID, note_id: uuid.UUID, db: Db, advocate: CurrentAdvocate
) -> None:
    note = await db.get(InternalNote, note_id)
    if note is None or note.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    if note.author_id != advocate.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "A note can only be removed by whoever wrote it"
        )
    await db.delete(note)
    await db.commit()


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    case_id: uuid.UUID, db: Db, _: CurrentAdvocate, include_done: bool = False
) -> list[Task]:
    """Outstanding first, in deadline order. Undated work sorts last rather than
    first: `NULLS LAST` because no deadline is not the most urgent thing."""
    stmt = select(Task).where(Task.case_id == case_id)
    if not include_done:
        stmt = stmt.where(Task.done_at.is_(None))
    stmt = stmt.order_by(Task.done_at.isnot(None), Task.due_on.asc().nulls_last(), Task.created_at)
    return list((await db.execute(stmt)).unique().scalars())


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def add_task(
    case_id: uuid.UUID, payload: TaskIn, db: Db, advocate: CurrentAdvocate
) -> Task:
    await _case_or_404(db, case_id)
    if await db.get(Advocate, payload.assignee_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Advocate not found")
    if payload.diary_entry_id is not None:
        entry = await db.get(DiaryEntry, payload.diary_entry_id)
        if entry is None or entry.case_id != case_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Diary entry not found")

    task = Task(
        case_id=case_id,
        title=payload.title.strip(),
        assignee_id=payload.assignee_id,
        created_by_id=advocate.id,
        due_date=payload.due_date,
        due_before_next_hearing=payload.due_before_next_hearing,
        diary_entry_id=payload.diary_entry_id,
    )
    db.add(task)
    await db.commit()
    return await _task_or_404(db, case_id, task.id)


async def _task_or_404(db: Db, case_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    # Re-selected rather than `db.get`, so that `due_on` - a column_property, and
    # so part of the SELECT rather than of the row - comes back populated.
    #
    # populate_existing for the same reason `load_case` needs it: the instance is
    # already in the identity map from the write just done, and without this its
    # joined relationships keep what they held then. Ticking a task off would
    # report the wrong `done_by`, or none.
    task = (
        (
            await db.execute(
                select(Task).where(Task.id == task_id).execution_options(populate_existing=True)
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if task is None or task.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def amend_task(
    case_id: uuid.UUID, task_id: uuid.UUID, payload: TaskUpdate, db: Db, advocate: CurrentAdvocate
) -> Task:
    """Anyone in the firm may tick anyone's Task off - authorship is recorded
    rather than permissions enforced. Who did it is kept."""
    task = await _task_or_404(db, case_id, task_id)
    data = payload.model_dump(exclude_unset=True)

    if (done := data.pop("done", None)) is not None:
        if done and task.done_at is None:
            task.done_at = dt.datetime.now(dt.timezone.utc)
            task.done_by_id = advocate.id
        elif not done:
            task.done_at = None
            task.done_by_id = None

    if data.get("assignee_id") is not None and await db.get(Advocate, data["assignee_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Advocate not found")

    for field, value in data.items():
        setattr(task, field, value)

    # Setting one kind of deadline clears the other, so the two can never both
    # be true even across two separate edits.
    if "due_date" in data and data["due_date"] is not None:
        task.due_before_next_hearing = False
    if data.get("due_before_next_hearing"):
        task.due_date = None

    await db.commit()
    return await _task_or_404(db, case_id, task_id)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_task(
    case_id: uuid.UUID, task_id: uuid.UUID, db: Db, _: CurrentAdvocate
) -> None:
    task = await _task_or_404(db, case_id, task_id)
    await db.delete(task)
    await db.commit()


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------


@router.get("/timeline", response_model=list[TimelineItem])
async def timeline(case_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> list[TimelineItem]:
    """Hearings and Diary Entries interleaved, most recent first.

    A reading order, not a record of its own - two entries on one date are normal
    rather than a duplicate to be reconciled.
    """
    hearings = (
        (await db.execute(select(Hearing).where(Hearing.case_id == case_id)))
        .unique()
        .scalars()
    )
    entries = (
        (await db.execute(select(DiaryEntry).where(DiaryEntry.case_id == case_id)))
        .unique()
        .scalars()
    )

    items: list[TimelineItem] = [
        TimelineHearing(date=h.date, hearing=HearingOut.model_validate(h)) for h in hearings
    ]
    items += [
        TimelineDiary(date=e.date, entry=DiaryEntryOut.model_validate(e)) for e in entries
    ]

    # Newest first; on a shared date the court's account reads above the note
    # written about it. Under reverse=True, True sorts before False, so the
    # second key tests for "hearing".
    items.sort(key=lambda i: (i.date, i.kind == "hearing"), reverse=True)
    return items
