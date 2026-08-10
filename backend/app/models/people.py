from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import PartyKind


class Advocate(UUIDMixin, TimestampMixin, Base):
    """A member of the firm who uses the system.

    All advocates read and write everything; there are no permissions. What the
    system relies on instead is attribution - every Diary Entry, Firm Status
    change and applied Snapshot names one of these.
    """

    __tablename__ = "advocates"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Clerk(UUIDMixin, TimestampMixin, Base):
    """A member of the firm recorded by name but who does not use the system.

    Named by an Advocate wherever the firm needs to say who is responsible for
    something - a Hearing's Representation, most likely - without that being
    the Advocate who appeared in court. No login of their own.
    """

    __tablename__ = "clerks"

    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Party(UUIDMixin, TimestampMixin, Base):
    """A person or organisation the firm has dealt with, recorded once and reused
    across every Case it appears in.

    A Party exists independently of any Case, which is what makes "every case for
    this client" and "every case against KSEB" answerable at all.
    """

    __tablename__ = "parties"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[PartyKind] = mapped_column(
        Enum(PartyKind, name="party_kind", native_enum=False, validate_strings=True),
        nullable=False,
        default=PartyKind.person,
    )
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
