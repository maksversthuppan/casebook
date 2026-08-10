from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import SESSION_KEY, CurrentAdvocate, Db
from app.models import Advocate
from app.schemas import AdvocateOut, LoginIn
from app.security import hash_password, needs_rehash, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AdvocateOut)
async def login(payload: LoginIn, request: Request, db: Db) -> Advocate:
    advocate = (
        await db.execute(select(Advocate).where(Advocate.email == payload.email.lower()))
    ).scalar_one_or_none()

    # Same response whether the email is unknown or the password is wrong.
    if advocate is None or not advocate.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    if not verify_password(payload.password, advocate.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")

    if needs_rehash(advocate.password_hash):
        advocate.password_hash = hash_password(payload.password)
        await db.commit()

    request.session.clear()
    request.session[SESSION_KEY] = str(advocate.id)
    return advocate


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me", response_model=AdvocateOut)
async def me(advocate: CurrentAdvocate) -> Advocate:
    return advocate


@router.get("/advocates", response_model=list[AdvocateOut])
async def list_advocates(db: Db, _: CurrentAdvocate) -> list[Advocate]:
    """Everyone in the firm, for assigning cases."""
    result = await db.execute(
        select(Advocate).where(Advocate.is_active.is_(True)).order_by(Advocate.name)
    )
    return list(result.scalars())
