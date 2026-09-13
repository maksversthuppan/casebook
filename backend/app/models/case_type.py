from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class CaseType(UUIDMixin, TimestampMixin, Base):
    """One case type as DCMS itself names it - "OP", "Crl.MP", and the like.

    One fixed vocabulary, the same regardless of which court is chosen. Learned
    opportunistically from the portal's own case-type dropdown whenever the
    ingestion wizard reads it, and kept from then on rather than re-fetched on
    every search - a filter needs the list to browse, not a live portal session.
    """

    __tablename__ = "case_types"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
