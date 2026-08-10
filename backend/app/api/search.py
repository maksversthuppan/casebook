"""One search box, and the home dashboard.

Both answer the same question from different ends: what should I be looking at.
Neither offers a filter builder - the firm is five people, and every extra
control is one more thing to get wrong before finding a case.
"""

import datetime as dt
import uuid

from fastapi import APIRouter
from sqlalchemy import String, cast, func, literal_column, or_, select

from app.api.deps import CurrentAdvocate, Db
from app.config import today_in_court
from app.models import (
    Assignment,
    Case,
    CaseParty,
    DiaryEntry,
    FirmStatus,
    Hearing,
    HearingState,
    InternalNote,
    Party,
    Task,
)
from app.schemas.search import Dashboard, DashboardHearing, SearchHit, SearchMatch

router = APIRouter(tags=["search"])

#: Postgres text-search configuration. English stemming suits the diary, which
#: is written in English even where the names in it are not.
#:
#: A `literal_column`, not a plain Python string: passed as a string it compiles
#: to a bind parameter, and no functional index can match a parameterised
#: expression - the GIN indexes in migration `63c137204a1f` would sit unused
#: while every search did a sequential scan.
TS_CONFIG = literal_column("'english'")

#: How long a Case may go unconfirmed before it is worth surfacing. Not a
#: correctness threshold - nothing is wrong with a stale Case, it is only
#: unconfirmed (CONTEXT.md, "Last Refreshed").
STALE_AFTER_DAYS = 30


def _headline(column, query):
    """A snippet of the matching text with the hit marked, so a search result
    says *why* it matched rather than making someone open the case to find out."""
    return func.ts_headline(
        TS_CONFIG,
        column,
        func.plainto_tsquery(TS_CONFIG, query),
        "StartSel=<<,StopSel=>>,MaxWords=18,MinWords=5,MaxFragments=1",
    )


@router.get("/search", response_model=list[SearchHit])
async def search(
    db: Db,
    advocate: CurrentAdvocate,
    q: str,
    firm_status: FirmStatus | None = None,
    mine: bool = False,
    limit: int = 50,
) -> list[SearchHit]:
    """One box over everything: court numbers, the people involved, and the
    firm's own writing.

    Identifiers match on substring, because half a case number is what anybody
    actually remembers. Diary entries and notes go through Postgres full-text,
    because those are prose and "adjournment" should find "adjourned".
    """
    term = q.strip()
    if not term:
        return []

    like = f"%{term}%"
    tsquery = func.plainto_tsquery(TS_CONFIG, term)

    # Each branch finds case ids and says why. Collected separately rather than
    # as one query, so a case matching three ways keeps all three reasons.
    reasons: dict[uuid.UUID, list[SearchMatch]] = {}

    def note(case_id: uuid.UUID, kind: str, snippet: str | None = None) -> None:
        reasons.setdefault(case_id, []).append(SearchMatch(kind=kind, snippet=snippet))

    identifiers = await db.execute(
        select(Case.id, Case.cino, Case.registration_number, Case.filing_number).where(
            or_(
                Case.cino.ilike(like),
                Case.registration_number.ilike(like),
                Case.filing_number.ilike(like),
                cast(Case.case_type, String).ilike(like),
            )
        )
    )
    for cid, cino, reg, fil in identifiers:
        note(cid, "identifier", reg or fil or cino)

    people = await db.execute(
        select(CaseParty.case_id, Party.name)
        .join(Party, Party.id == CaseParty.party_id)
        .where(Party.name.ilike(like))
    )
    for cid, name in people:
        note(cid, "party", name)

    diary = await db.execute(
        select(DiaryEntry.case_id, _headline(DiaryEntry.body, term)).where(
            func.to_tsvector(TS_CONFIG, DiaryEntry.body).op("@@")(tsquery)
        )
    )
    for cid, snippet in diary:
        note(cid, "diary", snippet)

    notes = await db.execute(
        select(InternalNote.case_id, _headline(InternalNote.body, term)).where(
            func.to_tsvector(TS_CONFIG, InternalNote.body).op("@@")(tsquery)
        )
    )
    for cid, snippet in notes:
        note(cid, "note", snippet)

    if not reasons:
        return []

    stmt = select(Case).where(Case.id.in_(reasons.keys()))
    if firm_status is not None:
        stmt = stmt.where(Case.firm_status == firm_status)
    if mine:
        stmt = stmt.where(
            Case.id.in_(select(Assignment.case_id).where(Assignment.advocate_id == advocate.id))
        )
    cases = list((await db.execute(stmt)).unique().scalars())

    # An identifier or a party name is what someone searching usually meant; a
    # phrase found in the diary is the fallback. Sorted so the obvious answer is
    # not buried under prose that happens to contain the word.
    def rank(case: Case) -> tuple[int, str]:
        kinds = {m.kind for m in reasons[case.id]}
        best = 0 if "identifier" in kinds else 1 if "party" in kinds else 2
        return (best, case.created_at.isoformat())

    cases.sort(key=rank)
    return [SearchHit(case=c, matches=reasons[c.id]) for c in cases[:limit]]


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(db: Db, advocate: CurrentAdvocate, days: int = 7) -> Dashboard:
    """What the signed-in advocate should be looking at today.

    "Mine" means a Case this advocate holds an Assignment on - the standing
    roster, not who happens to be down for one Hearing. Relinquished and closed
    Cases are absent throughout: this is a view of work in hand.
    """
    today = today_in_court()
    horizon = today + dt.timedelta(days=days)

    working = (FirmStatus.active, FirmStatus.on_hold)
    my_cases = select(Assignment.case_id).where(Assignment.advocate_id == advocate.id)

    # Hearings this week, on my cases. Scheduled only - a date already dealt
    # with is not something to prepare for.
    upcoming = (
        await db.execute(
            select(Hearing, Case)
            .join(Case, Case.id == Hearing.case_id)
            .where(
                Hearing.case_id.in_(my_cases),
                Hearing.state == HearingState.scheduled,
                Hearing.date >= today,
                Hearing.date <= horizon,
                Case.firm_status.in_(working),
            )
            .order_by(Hearing.date)
        )
    ).unique()

    # A scheduled date that has passed with nothing recorded against it. Kept
    # apart from the week ahead because it means something different: not work
    # coming, but a record with a hole in it.
    overdue = (
        await db.execute(
            select(Hearing, Case)
            .join(Case, Case.id == Hearing.case_id)
            .where(
                Hearing.case_id.in_(my_cases),
                Hearing.state == HearingState.scheduled,
                Hearing.date < today,
                Case.firm_status.in_(working),
            )
            .order_by(Hearing.date.desc())
        )
    ).unique()

    # Tasks I owe. Undated ones are included - work owed with no deadline is
    # still owed - and sort last.
    tasks = (
        await db.execute(
            select(Task)
            .join(Case, Case.id == Task.case_id)
            .where(
                Task.assignee_id == advocate.id,
                Task.done_at.is_(None),
                Case.firm_status.in_(working),
            )
            .order_by(Task.due_on.asc().nulls_last(), Task.created_at)
        )
    ).unique()

    # Cases nobody has confirmed with the court in a while. Never-refreshed
    # first: those have never been checked at all.
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=STALE_AFTER_DAYS)
    stale = (
        await db.execute(
            select(Case)
            .where(
                Case.id.in_(my_cases),
                Case.firm_status == FirmStatus.active,
                or_(Case.last_refreshed_at.is_(None), Case.last_refreshed_at < cutoff),
            )
            .order_by(Case.last_refreshed_at.asc().nulls_first())
            .limit(20)
        )
    ).unique()

    return Dashboard(
        today=today,
        horizon=horizon,
        stale_after_days=STALE_AFTER_DAYS,
        hearings=[DashboardHearing(hearing=h, case=c) for h, c in upcoming],
        hearings_passed=[DashboardHearing(hearing=h, case=c) for h, c in overdue],
        tasks=list(tasks.scalars()),
        stale_cases=list(stale.scalars()),
    )
