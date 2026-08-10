import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentAdvocate, Db
from app.models import Case, CaseParty, Party
from app.schemas import CaseSummary, PartyIn, PartyOut
from app.schemas.people import PartyUpdate

router = APIRouter(prefix="/parties", tags=["parties"])


@router.get("", response_model=list[PartyOut])
async def list_parties(db: Db, _: CurrentAdvocate, q: str | None = None, limit: int = 20) -> list[Party]:
    """Search-or-create picker. Typing a name finds the existing Party rather than
    making a second one, which is what keeps 'all cases for this client' honest."""
    stmt = select(Party).order_by(Party.name).limit(min(limit, 100))
    if q:
        stmt = stmt.where(Party.name.ilike(f"%{q.strip()}%"))
    return list((await db.execute(stmt)).scalars())


@router.post("", response_model=PartyOut, status_code=status.HTTP_201_CREATED)
async def create_party(payload: PartyIn, db: Db, _: CurrentAdvocate) -> Party:
    party = Party(**payload.model_dump())
    db.add(party)
    await db.commit()
    return party


@router.get("/{party_id}", response_model=PartyOut)
async def get_party(party_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> Party:
    party = await db.get(Party, party_id)
    if party is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")
    return party


@router.patch("/{party_id}", response_model=PartyOut)
async def update_party(
    party_id: uuid.UUID, payload: PartyUpdate, db: Db, _: CurrentAdvocate
) -> Party:
    """A phone number, an address, a standing note about the person.

    These belong to the Party and travel with them across every Case they appear
    in. Anything true of one Case only is an Internal Note on that Case
    (CONTEXT.md, "Party").
    """
    party = await db.get(Party, party_id)
    if party is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(party, field, (value.strip() or None) if isinstance(value, str) else value)

    await db.commit()
    await db.refresh(party)
    return party


@router.get("/{party_id}/cases", response_model=list[CaseSummary])
async def cases_for_party(party_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> list[Case]:
    """Every Case this Party appears in, whichever side they were on.

    This is what the Party entity buys us: without it, "everything for Rajan" or
    "everything against KSEB" would be a text search over duplicated names.
    """
    stmt = (
        select(Case)
        .join(CaseParty, CaseParty.case_id == Case.id)
        .where(CaseParty.party_id == party_id)
        .order_by(Case.created_at.desc())
    )
    return list((await db.execute(stmt)).unique().scalars())
