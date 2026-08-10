"""Clerks - firm members recorded by name, with no login of their own.

Existing only to be picked as a Hearing's Representation when the point is
who to ask, not which Advocate stood up (CONTEXT.md, "Clerk").
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentAdvocate, Db
from app.models import Clerk
from app.schemas import ClerkIn, ClerkOut

router = APIRouter(prefix="/clerks", tags=["clerks"])


@router.get("", response_model=list[ClerkOut])
async def list_clerks(db: Db, _: CurrentAdvocate) -> list[Clerk]:
    return list((await db.execute(select(Clerk).order_by(Clerk.name))).scalars())


@router.post("", response_model=ClerkOut, status_code=status.HTTP_201_CREATED)
async def create_clerk(payload: ClerkIn, db: Db, _: CurrentAdvocate) -> Clerk:
    clerk = Clerk(name=payload.name.strip())
    db.add(clerk)
    await db.commit()
    return clerk


@router.get("/{clerk_id}", response_model=ClerkOut)
async def get_clerk(clerk_id: uuid.UUID, db: Db, _: CurrentAdvocate) -> Clerk:
    clerk = await db.get(Clerk, clerk_id)
    if clerk is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clerk not found")
    return clerk
