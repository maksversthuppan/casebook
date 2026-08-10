import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.court import Court
from app.models.enums import AdvocateRole, FirmStatus, PartyRole, RelationKind
from app.models.people import Advocate, Party


class Case(UUIDMixin, TimestampMixin, Base):
    """One proceeding before one court.

    Identity is the internal id and nothing else. CINO is unique when present but
    may be absent - a Case created on filing day has no CINO, and learns it from
    its first DCMS search. Filing and registration numbers are labels that change.
    """

    __tablename__ = "cases"
    __table_args__ = (
        # A Vakalath names exactly one holder - never a firm Advocate and an
        # outside name at once. Neither set means no Vakalath is recorded.
        CheckConstraint(
            "NOT (vakalath_advocate_id IS NOT NULL AND vakalath_holder_name IS NOT NULL)",
            name="ck_case_vakalath_one_holder",
        ),
    )

    # Unique when present; Postgres permits many NULLs in a unique index, which is
    # exactly the behaviour wanted here.
    cino: Mapped[str | None] = mapped_column(String(32), unique=True)
    filing_number: Mapped[str | None] = mapped_column(String(100))
    # Days, not moments - the day the papers were presented and the day the court
    # registered them, the same kind of thing as a Hearing's date. Held as
    # timestamps until 2026-08-10, which read every one of them a day early: a
    # date written to a `timestamptz` becomes IST midnight, and IST midnight
    # read back as UTC is the previous evening. The portal's own dates have the
    # same trap on the way in (`flight._parse_portal_date`).
    filing_date: Mapped[date | None] = mapped_column(Date)
    registration_number: Mapped[str | None] = mapped_column(String(100))
    registration_date: Mapped[date | None] = mapped_column(Date)
    case_type: Mapped[str | None] = mapped_column(String(100))

    court_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courts.id", ondelete="RESTRICT"), nullable=False
    )

    # The court's word, in the portal's own vocabulary. Free text on purpose: these
    # values belong to DCMS, and inventing an enum for them would misrepresent
    # anything the portal says that we did not anticipate.
    court_status: Mapped[str | None] = mapped_column(String(200))

    # The firm's own view, which legitimately disagrees with the court's. Every
    # list and dashboard filters on this one (ADR-0002).
    firm_status: Mapped[FirmStatus] = mapped_column(
        Enum(FirmStatus, name="firm_status", native_enum=False, validate_strings=True),
        nullable=False,
        default=FirmStatus.active,
    )

    # When the court-sourced fields above were last confirmed against DCMS.
    # Null means never: nothing here has been checked with the portal at all.
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The Vakalath: the firm's own claim about who is on record, and the one name
    # it stands in - either an Advocate of the firm or somebody outside it, never
    # both, at most one per Case. Deliberately separate from the advocate the
    # portal names for our own side: those are two claims about the same fact,
    # and where they disagree that is worth seeing (ADR-0008). Firm-entered, so
    # a Refresh never touches it (rule 1, ADR-0007). "Yes/no" is read off whether
    # a holder is present - there is no boolean to contradict the name.
    vakalath_advocate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )
    vakalath_holder_name: Mapped[str | None] = mapped_column(String(200))

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )

    court: Mapped[Court] = relationship(lazy="joined")
    vakalath_advocate: Mapped[Advocate | None] = relationship(
        lazy="joined", foreign_keys=[vakalath_advocate_id]
    )
    parties: Mapped[list["CaseParty"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    tags: Mapped[list["Tag"]] = relationship(secondary="case_tags", lazy="selectin")

    # Present only where the court records one; most Cases have none (ADR-0006).
    crime_details: Mapped["CrimeDetail | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    # A list, not a scalar - a Case can be brought under several (ADR-0006).
    act_sections: Mapped[list["ActSection"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ActSection.act_name"
    )


class FirmStatusChange(UUIDMixin, TimestampMixin, Base):
    """One change of a Case's Firm Status: what it was, what it became, which
    Advocate decided, when, and why if they said.

    Append-only - nothing here is ever edited or deleted. `created_at` is the
    moment the change was made, there being no difference between recording it
    and making it.

    CONTEXT.md has claimed from the beginning that a Firm Status change is
    attributed to an Advocate. Until this table it was not: `firm_status` was a
    bare column and every change overwrote the last, leaving no trace of who or
    when. A Case reading "relinquished" invites exactly one question, and the
    answer should not depend on somebody remembering.

    Deliberately not part of the Timeline: the Timeline is what the court and the
    advocates did about the Case, and this is the firm's own bookkeeping about
    it (CONTEXT.md, "Firm Status History").
    """

    __tablename__ = "firm_status_changes"

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Null on the first entry: before the Case existed it had no status. Every
    #: Case gets one of these at creation, however it was created.
    from_status: Mapped[FirmStatus | None] = mapped_column(
        Enum(FirmStatus, name="firm_status", native_enum=False, validate_strings=True)
    )
    to_status: Mapped[FirmStatus] = mapped_column(
        Enum(FirmStatus, name="firm_status", native_enum=False, validate_strings=True),
        nullable=False,
    )
    #: Nullable only so that removing an Advocate does not take the history with
    #: them. Always set when written.
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advocates.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)

    changed_by: Mapped[Advocate | None] = relationship(lazy="joined")


class CaseParty(UUIDMixin, TimestampMixin, Base):
    """A Party's role in one Case.

    Client and Opposite Party are roles here, not kinds of thing - the same Party
    may be a client in one Case and an opponent in another.
    """

    __tablename__ = "case_parties"
    __table_args__ = (UniqueConstraint("case_id", "party_id", "role", name="uq_case_party_role"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[PartyRole] = mapped_column(
        Enum(PartyRole, name="party_role", native_enum=False, validate_strings=True), nullable=False
    )
    # Cause-title order, so parties read as they do on the papers.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # What the portal called this party, kept verbatim beside the firm's own link
    # ("RAJAN K S/O KRISHNAN"). The link is a person's judgement; this is evidence.
    portal_raw_name: Mapped[str | None] = mapped_column(Text)

    case: Mapped[Case] = relationship(back_populates="parties")
    party: Mapped[Party] = relationship(lazy="joined")
    # The other side's lawyer, as the portal names them - never a system user,
    # and a CaseParty may carry several at once.
    counsels: Mapped[list["Counsel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="Counsel.name"
    )


class Counsel(UUIDMixin, TimestampMixin, Base):
    """The other side's lawyer, as the portal names them against a CaseParty.

    Never a system user (CONTEXT.md). A CaseParty may carry several - counsel
    can change over a Case's life without one entry replacing another.
    """

    __tablename__ = "counsels"
    __table_args__ = (UniqueConstraint("case_party_id", "name", name="uq_counsel_case_party_name"),)

    case_party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case_parties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    registration: Mapped[str | None] = mapped_column(String(100))


class CrimeDetail(UUIDMixin, TimestampMixin, Base):
    """The police case a Case relates to, as the portal reports it.

    One-to-one and optional: present only where the court records one.
    Reported by DCMS, displayed as the court's word, never edited here - the
    same footing as Court Status (ADR-0006).
    """

    __tablename__ = "crime_details"

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    cr_no: Mapped[str | None] = mapped_column(String(100))
    fir_no: Mapped[str | None] = mapped_column(String(100))
    fir_year: Mapped[int | None] = mapped_column(Integer)
    fir_date: Mapped[date | None] = mapped_column(Date)
    investigating_officer: Mapped[str | None] = mapped_column(String(200))
    police_station: Mapped[str | None] = mapped_column(String(300))
    rank: Mapped[str | None] = mapped_column(String(100))


class ActSection(UUIDMixin, TimestampMixin, Base):
    """One law and section a Case is brought under, as the portal pairs them.

    A Case carries a list of these, replaced wholesale by every Ingestion and
    Refresh - never merged one at a time (rule 2, ADR-0006).
    """

    __tablename__ = "act_sections"

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    act_code: Mapped[str | None] = mapped_column(String(50))
    act_name: Mapped[str] = mapped_column(String(300), nullable=False)
    section: Mapped[str | None] = mapped_column(String(100))


class Assignment(UUIDMixin, TimestampMixin, Base):
    """An Advocate's standing involvement in a Case, held as a role.

    Any Case where an Advocate holds a role is one of their own cases, so a junior
    doing the drafting does not lose sight of work they do not lead.
    """

    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("case_id", "advocate_id", name="uq_assignment"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    advocate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advocates.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[AdvocateRole] = mapped_column(
        Enum(AdvocateRole, name="advocate_role", native_enum=False, validate_strings=True),
        nullable=False,
    )

    case: Mapped[Case] = relationship(back_populates="assignments")
    advocate: Mapped[Advocate] = relationship(lazy="joined")


class CaseRelation(UUIDMixin, TimestampMixin, Base):
    """How one proceeding arose from another.

    Reads left to right: case `kind` related_case, as in "AS/88/2025 is an
    appeal_of OS/412/2024". Cases stay independent records; this only lets an
    advocate walk between them (ADR-0001).
    """

    __tablename__ = "case_relations"
    __table_args__ = (
        UniqueConstraint("case_id", "related_case_id", "kind", name="uq_case_relation"),
        CheckConstraint("case_id <> related_case_id", name="ck_case_relation_not_self"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    related_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[RelationKind] = mapped_column(
        Enum(RelationKind, name="relation_kind", native_enum=False, validate_strings=True),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text)


class Tag(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class CaseTag(Base):
    __tablename__ = "case_tags"

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
