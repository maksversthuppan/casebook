import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.enums import PartyKind


class AdvocateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class PartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    kind: PartyKind = PartyKind.person
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    notes: str | None = None


class PartyUpdate(BaseModel):
    """What the firm knows about a person, corrected or filled in after the fact.

    Every field optional and unset means untouched, so a screen that edits only
    a phone number posts only a phone number. `kind` is absent: person or
    organisation is decided when the Party is created and is not the sort of
    thing corrected in passing.
    """

    model_config = ConfigDict(extra="forbid")

    #: Stripped and required non-empty when given - a Party with a blank name
    #: cannot be found again, and the column is not nullable.
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
        | None
    ) = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    notes: str | None = None


class PartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: PartyKind
    phone: str | None
    email: str | None
    address: str | None
    notes: str | None


class ClerkIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ClerkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
