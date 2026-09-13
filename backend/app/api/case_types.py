from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentAdvocate, Db
from app.models import CaseType
from app.schemas import CaseTypeOut

router = APIRouter(prefix="/case-types", tags=["case-types"])


@router.get("", response_model=list[CaseTypeOut])
async def list_case_types(db: Db, _: CurrentAdvocate) -> list[CaseType]:
    """The case types DCMS itself offers, for the filter on the search screen.

    Nothing here talks to the portal - these are learned opportunistically at
    Ingestion (`choose_court`) and simply read back here.
    """
    stmt = select(CaseType).order_by(CaseType.code)
    return list((await db.execute(stmt)).scalars())
