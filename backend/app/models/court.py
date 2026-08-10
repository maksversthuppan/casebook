from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Court(UUIDMixin, TimestampMixin, Base):
    """A single court establishment before which Cases proceed.

    Every DCMS search begins by choosing a district and a court, so a Court must
    be named exactly as the portal names it before any Case there can be searched
    at all (ADR-0004).

    A Court is *provisional* while it is only a name somebody typed, and
    *complete* once its portal values are recorded - which happens at Ingestion
    (ADR-0005). Only a complete Court can be searched.
    """

    __tablename__ = "courts"

    # The firm's own label, e.g. "EKM Munsiff Court". Free to be shorter than the
    # portal's name, which advocates do not use in conversation.
    name: Mapped[str] = mapped_column(String(300), nullable=False)

    # Exactly what was chosen from the portal's cascading dropdowns. Recorded
    # verbatim so Playwright can re-select it without guessing.
    portal_state: Mapped[str | None] = mapped_column(String(100))
    portal_district: Mapped[str | None] = mapped_column(String(150))
    portal_establishment: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        # Two complete Courts may not claim the same establishment. Provisional
        # Courts are exempt: they are only names, and duplicates among them get
        # folded in when one is completed.
        Index(
            "uq_courts_portal_identity",
            "portal_district",
            "portal_establishment",
            unique=True,
            postgresql_where=text(
                "portal_district IS NOT NULL AND portal_establishment IS NOT NULL"
            ),
        ),
    )

    @property
    def is_complete(self) -> bool:
        return bool(self.portal_state and self.portal_district and self.portal_establishment)
