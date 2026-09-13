import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentAdvocate, Db
from app.models import (
    Advocate,
    Assignment,
    Case,
    CaseParty,
    CaseRelation,
    FirmStatus,
    FirmStatusChange,
    Party,
)
from app.models.enums import RelationKind
from app.schemas import (
    CaseCreate,
    CaseDetail,
    CaseSummary,
    CaseUpdate,
    FirmStatusChangeOut,
    VakalathIn,
)
from app.schemas.case import CaseRelationOut
from app.services.cases import create_case, load_case, update_case

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=list[CaseSummary])
async def list_cases(
    db: Db,
    advocate: CurrentAdvocate,
    q: str | None = None,
    firm_status: FirmStatus | None = None,
    case_type: str | None = None,
    court_id: uuid.UUID | None = None,
    mine: bool = False,
) -> list[Case]:
    """The case list.

    Filters on Firm Status, never Court Status - a disposed case under appeal is
    the firm's most active work (ADR-0002).
    """
    stmt = select(Case).order_by(Case.created_at.desc())

    if firm_status is not None:
        stmt = stmt.where(Case.firm_status == firm_status)

    if case_type is not None:
        stmt = stmt.where(Case.case_type == case_type)

    if court_id is not None:
        stmt = stmt.where(Case.court_id == court_id)

    if mine:
        stmt = stmt.where(
            Case.id.in_(
                select(Assignment.case_id).where(Assignment.advocate_id == advocate.id)
            )
        )

    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Case.cino.ilike(term),
                Case.registration_number.ilike(term),
                Case.filing_number.ilike(term),
                Case.id.in_(
                    select(CaseParty.case_id)
                    .join(Party, Party.id == CaseParty.party_id)
                    .where(Party.name.ilike(term))
                ),
            )
        )

    return list((await db.execute(stmt)).unique().scalars())


@router.post("", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
async def create(payload: CaseCreate, db: Db, advocate: CurrentAdvocate) -> Case:
    """Manual creation - court, one client, one advocate. Everything else is
    optional, including every court-issued number."""
    return await create_case(db, payload, advocate)


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case(case_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> Case:
    case = await load_case(db, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


@router.patch("/{case_id}", response_model=CaseDetail)
async def patch_case(
    case_id: uuid.UUID, payload: CaseUpdate, db: Db, advocate: CurrentAdvocate
) -> Case:
    """The advocate is not decoration here: a Firm Status change is attributed to
    whoever made it, and this is where that is known."""
    case = await load_case(db, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return await update_case(db, case, payload, advocate)


@router.get("/{case_id}/firm-status-history", response_model=list[FirmStatusChangeOut])
async def firm_status_history(
    case_id: uuid.UUID, db: Db, _: CurrentAdvocate
) -> list[FirmStatusChange]:
    """Every Firm Status this Case has been through, newest first.

    A Case reading "relinquished" invites exactly one question, and this answers
    it. Its own endpoint rather than part of `CaseDetail` so the case *list* does
    not carry a history it never shows.
    """
    stmt = (
        select(FirmStatusChange)
        .where(FirmStatusChange.case_id == case_id)
        .order_by(FirmStatusChange.created_at.desc())
    )
    return list((await db.execute(stmt)).unique().scalars())


@router.put("/{case_id}/vakalath", response_model=CaseDetail)
async def set_vakalath(
    case_id: uuid.UUID, payload: VakalathIn, db: Db, _: CurrentAdvocate
) -> Case:
    """Who the firm says is on record in this Case - an Advocate of the firm, or
    an outside name it is assisting under. Give neither to clear it.

    The firm's own claim, deliberately not reconciled with the advocate the
    portal names for our side (ADR-0008), and firm-entered so no Refresh touches
    it (rule 1, ADR-0007).
    """
    case = await load_case(db, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    if payload.advocate_id is not None and await db.get(Advocate, payload.advocate_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Advocate not found")

    case.vakalath_advocate_id = payload.advocate_id
    case.vakalath_holder_name = (payload.holder_name or "").strip() or None
    await db.commit()
    return await load_case(db, case_id)


@router.get("/{case_id}/relations", response_model=list[CaseRelationOut])
async def list_relations(case_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> list[CaseRelation]:
    stmt = select(CaseRelation).where(CaseRelation.case_id == case_id)
    return list((await db.execute(stmt)).scalars())


@router.post(
    "/{case_id}/relations", response_model=CaseRelationOut, status_code=status.HTTP_201_CREATED
)
async def add_relation(
    case_id: uuid.UUID,
    related_case_id: uuid.UUID,
    kind: RelationKind,
    db: Db,
    _: CurrentAdvocate,
    note: str | None = None,
) -> CaseRelation:
    """Reads left to right: this case `kind` the related case, as in
    'AS/88/2025 is an appeal_of OS/412/2024'."""
    if case_id == related_case_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A case cannot relate to itself")

    for cid in (case_id, related_case_id):
        if await load_case(db, cid) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Case {cid} not found")

    relation = CaseRelation(
        case_id=case_id, related_case_id=related_case_id, kind=kind, note=note
    )
    db.add(relation)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That relation already exists") from exc
    return relation


@router.delete("/{case_id}/relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_relation(
    case_id: uuid.UUID, relation_id: uuid.UUID, db: Db, _: CurrentAdvocate
) -> None:
    relation = await db.get(CaseRelation, relation_id)
    if relation is None or relation.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relation not found")
    await db.delete(relation)
    await db.commit()
