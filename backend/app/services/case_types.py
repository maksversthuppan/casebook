from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CaseType


async def record_case_types(db: AsyncSession, codes: list[str]) -> None:
    """Learn from whatever the portal's case-type dropdown just offered.

    Called opportunistically from `choose_court` - there is no dedicated
    one-off pull. The list is the same regardless of which court is chosen, so
    every ingestion session that reads it fills in anything still missing.
    """
    seen = {c.strip() for c in codes if c.strip()}
    if not seen:
        return

    known = {
        c.code for c in (await db.execute(select(CaseType).where(CaseType.code.in_(seen)))).scalars()
    }
    for code in seen - known:
        db.add(CaseType(code=code))
    await db.commit()
