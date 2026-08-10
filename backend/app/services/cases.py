import uuid
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Advocate,
    Assignment,
    Case,
    CaseParty,
    Court,
    FirmStatus,
    FirmStatusChange,
    Party,
    Tag,
)
from app.schemas import AssignmentIn, CaseCreate, CaseUpdate
from app.schemas.people import PartyIn


class _PartySpec(Protocol):
    """What `_resolve_party` needs - `CasePartyIn` and the ingest review's own
    party spec both shape up this way, without either importing the other."""

    party_id: uuid.UUID | None
    new_party: PartyIn | None


async def load_case(db: AsyncSession, case_id: uuid.UUID) -> Case | None:
    # populate_existing: the instance is usually already in the identity map from
    # the write we just did, and without this its collections keep whatever they
    # held then rather than what is now in the database.
    # .unique() because court and party are joined-eager-loaded.
    result = await db.execute(
        select(Case).where(Case.id == case_id).execution_options(populate_existing=True)
    )
    return result.unique().scalar_one_or_none()


async def _resolve_court(db: AsyncSession, payload: CaseCreate) -> Court:
    if payload.court_id is not None:
        court = await db.get(Court, payload.court_id)
        if court is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Court not found")
        return court

    # A court added inline is provisional: a name only. It gains its portal
    # district and establishment the first time a Case there is ingested.
    court = Court(name=payload.new_court_name.strip())
    db.add(court)
    await db.flush()
    return court


async def _resolve_party(db: AsyncSession, spec: _PartySpec) -> Party:
    if spec.party_id is not None:
        party = await db.get(Party, spec.party_id)
        if party is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Party {spec.party_id} not found")
        return party

    party = Party(**spec.new_party.model_dump())
    db.add(party)
    await db.flush()
    return party


def _check_unique_advocates(assignments: list[AssignmentIn]) -> None:
    ids = [a.advocate_id for a in assignments]
    if len(set(ids)) != len(ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An advocate may hold only one role")


async def _advocates_exist(db: AsyncSession, ids: list[uuid.UUID]) -> None:
    found = set((await db.execute(select(Advocate.id).where(Advocate.id.in_(ids)))).scalars())
    if missing := set(ids) - found:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Advocate not found: {', '.join(str(m) for m in missing)}"
        )


async def _resolve_tags(db: AsyncSession, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        tag = (await db.execute(select(Tag).where(Tag.name == name))).scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            await db.flush()
        tags.append(tag)
    return tags


def record_firm_status(
    db: AsyncSession,
    case_id: uuid.UUID,
    *,
    from_status: FirmStatus | None,
    to_status: FirmStatus,
    changed_by: Advocate,
    reason: str | None = None,
) -> FirmStatusChange:
    """The one place a Firm Status change is written down.

    Every route to a Firm Status goes through here - manual creation, Ingestion,
    and every later change - so the history has no gaps to explain. Call it
    *after* the Case has been flushed, so `case_id` exists to point at.

    Not a `Case` method and not an event listener on purpose: attribution needs
    the Advocate who decided, and the ORM has no idea who that is.
    """
    change = FirmStatusChange(
        case_id=case_id,
        from_status=from_status,
        to_status=to_status,
        changed_by_id=changed_by.id,
        reason=(reason.strip() or None) if reason else None,
    )
    db.add(change)
    return change


async def create_case(db: AsyncSession, payload: CaseCreate, created_by: Advocate) -> Case:
    court = await _resolve_court(db, payload)

    advocate_ids = [a.advocate_id for a in payload.assignments]
    _check_unique_advocates(payload.assignments)
    await _advocates_exist(db, advocate_ids)

    case = Case(
        court_id=court.id,
        cino=payload.cino.strip() if payload.cino else None,
        filing_number=payload.filing_number,
        filing_date=payload.filing_date,
        registration_number=payload.registration_number,
        registration_date=payload.registration_date,
        case_type=payload.case_type,
        firm_status=payload.firm_status,
        created_by_id=created_by.id,
    )
    case.tags = await _resolve_tags(db, payload.tags)
    db.add(case)

    # The whole write is guarded: a duplicate CINO surfaces at flush, not commit.
    try:
        await db.flush()

        for spec in payload.parties:
            party = await _resolve_party(db, spec)
            db.add(
                CaseParty(
                    case_id=case.id, party_id=party.id, role=spec.role, position=spec.position
                )
            )

        for spec in payload.assignments:
            db.add(Assignment(case_id=case.id, advocate_id=spec.advocate_id, role=spec.role))

        # The opening entry: from nothing, because before this the Case had no
        # status to change from.
        record_firm_status(
            db,
            case.id,
            from_status=None,
            to_status=payload.firm_status,
            changed_by=created_by,
        )

        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "cases_cino_key" in str(exc.orig):
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"A case with CINO {payload.cino} already exists"
            ) from exc
        raise

    return await load_case(db, case.id)


async def update_case(
    db: AsyncSession, case: Case, payload: CaseUpdate, changed_by: Advocate
) -> Case:
    """Applies only what the firm owns.

    Court Status, CINO and the hearing record are not reachable from here - they
    change by applying a DCMS Snapshot, never by hand (ADR-0002).
    """
    data = payload.model_dump(exclude_unset=True)
    tags = data.pop("tags", None)
    # Describes the change, not the Case, so it goes on the history entry and
    # never onto a column of `cases`.
    reason = data.pop("firm_status_reason", None)

    # Read before the loop overwrites it. A status set to what it already was is
    # not a change and leaves no entry - otherwise saving an unrelated edit from
    # a form that posts every field would litter the history.
    previous = case.firm_status
    new_status = data.get("firm_status")

    for field, value in data.items():
        setattr(case, field, value)
    if tags is not None:
        case.tags = await _resolve_tags(db, tags)

    if new_status is not None and new_status != previous:
        record_firm_status(
            db,
            case.id,
            from_status=previous,
            to_status=new_status,
            changed_by=changed_by,
            reason=reason,
        )

    await db.commit()
    return await load_case(db, case.id)
