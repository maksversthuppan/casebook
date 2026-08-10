"""What the portal said, and when.

A Snapshot is written the moment a response arrives, before anything is parsed
out of it. The advocate paid a CAPTCHA for that response; a parse failure must
leave evidence rather than nothing. See ADR-0003 and ADR-0005.
"""

import datetime as dt
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.court import Court
from app.models.enums import SearchMode, SnapshotStatus
from app.models.people import Advocate


class DcmsSnapshot(UUIDMixin, TimestampMixin, Base):
    """What DCMS said about one Case at one moment, recorded exactly as received.

    Never altered afterwards. Raw responses accumulate into the parser's
    regression corpus, so the first real ingestions pay for the test fixtures.
    """

    __tablename__ = "dcms_snapshots"

    #: Null during Ingestion: the Snapshot exists before the Case it will create.
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    #: The court that was selected before searching. Required, because the portal
    #: will not run any search until a district and court are chosen (ADR-0004).
    court_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courts.id", ondelete="SET NULL")
    )

    search_mode: Mapped[SearchMode] = mapped_column(
        Enum(SearchMode, name="search_mode", native_enum=False, validate_strings=True),
        nullable=False,
    )
    search_value: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Only set for the Case No / Filing No tabs. Recorded so a "not found"
    #: result is diagnosable afterwards, without having to guess what was typed.
    search_case_type: Mapped[str | None] = mapped_column(String(200))
    search_year: Mapped[str | None] = mapped_column(String(10))

    #: Exactly what came back, before parsing. Never re-encoded.
    raw_response: Mapped[str | None] = mapped_column(Text)
    #: What we made of it. Null if parsing failed, in which case parse_error says why.
    parsed: Mapped[dict | None] = mapped_column(JSONB)
    parse_error: Mapped[str | None] = mapped_column(Text)

    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )

    status: Mapped[SnapshotStatus] = mapped_column(
        Enum(SnapshotStatus, name="snapshot_status", native_enum=False, validate_strings=True),
        nullable=False,
        default=SnapshotStatus.captured,
    )
    #: Set when applied or rejected - who decided, and when.
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )

    court: Mapped[Court | None] = relationship(lazy="joined")
    fetched_by: Mapped[Advocate | None] = relationship(
        lazy="joined", foreign_keys=[fetched_by_id]
    )
    decided_by: Mapped[Advocate | None] = relationship(
        lazy="joined", foreign_keys=[decided_by_id]
    )
