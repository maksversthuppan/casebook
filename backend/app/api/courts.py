from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentAdvocate, Db
from app.models import Court
from app.schemas import CourtIn, CourtOut

router = APIRouter(prefix="/courts", tags=["courts"])


@router.get("", response_model=list[CourtOut])
async def list_courts(db: Db, _: CurrentAdvocate, q: str | None = None) -> list[Court]:
    """The firm's own courts, for the picker on the case form.

    Only courts the firm actually appears in are ever recorded - there is no seeded
    list of every establishment in Kerala.
    """
    stmt = select(Court).order_by(Court.name)
    if q:
        stmt = stmt.where(Court.name.ilike(f"%{q.strip()}%"))
    return list((await db.execute(stmt)).scalars())


@router.post("", response_model=CourtOut, status_code=status.HTTP_201_CREATED)
async def create_court(payload: CourtIn, db: Db, _: CurrentAdvocate) -> Court:
    """Adds a provisional Court - a name and nothing else.

    It cannot be searched on DCMS until Ingestion records which district and
    establishment it is on the portal.
    """
    court = Court(name=payload.name.strip())
    db.add(court)
    await db.commit()
    return court
