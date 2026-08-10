import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Advocate

SESSION_KEY = "advocate_id"


async def current_advocate(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> Advocate:
    """The signed-in Advocate.

    Every advocate may read and write everything; there is no authorisation layer
    to consult. What this is for is attribution - knowing whose name goes on a
    Diary Entry, a Firm Status change or an applied Snapshot.
    """
    raw_id = request.session.get(SESSION_KEY)
    if not raw_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    try:
        advocate_id = uuid.UUID(raw_id)
    except ValueError:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in") from None

    advocate = await db.get(Advocate, advocate_id)
    if advocate is None or not advocate.is_active:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    return advocate


CurrentAdvocate = Annotated[Advocate, Depends(current_advocate)]
Db = Annotated[AsyncSession, Depends(get_db)]
