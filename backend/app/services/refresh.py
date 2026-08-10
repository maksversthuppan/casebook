"""Applying a later Snapshot to a Case that already exists.

Ingestion and Refresh are the same act (CONTEXT.md, "Ingestion") - the
difference is only that here there is something to compare against, and
therefore something for a person to look at before deciding.

The plan is built once and read twice: the diff screen renders it, and applying
executes it. They cannot drift apart, which is what makes "apply all or
discard" (rule 2) an honest offer rather than a hope. What a Refresh may write
and what it must never touch is ADR-0007.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dcms.flight import (
    PortalActSection,
    PortalCase,
    PortalCaseDetail,
    PortalCounsel,
    PortalCrimeDetails,
    extract_case,
    extract_case_detail,
    split_responses,
)
from app.models import (
    ActSection,
    Advocate,
    Case,
    CaseParty,
    Counsel,
    CrimeDetail,
    DcmsSnapshot,
    Hearing,
)
from app.models.enums import HearingSource, HearingState, SnapshotStatus
from app.schemas.refresh import (
    FieldChangeOut,
    HearingChangeOut,
    HearingFaceOut,
    ListChangeOut,
    RefreshDiffOut,
)
from app.services.cases import load_case
from app.services.ingest import hearings_from_snapshot

#: The Case columns a Refresh owns, as (attribute, label). All court-issued:
#: the status the court gives the case, the labels it gives the papers, and the
#: type it registered it under. Firm Status is deliberately absent (ADR-0007).
CASE_FIELDS: list[tuple[str, str]] = [
    ("court_status", "Court Status"),
    ("case_type", "Case type"),
    ("registration_number", "Registration number"),
    ("registration_date", "Registration date"),
    ("filing_number", "Filing number"),
    ("filing_date", "Filing date"),
]

CRIME_FIELDS: list[tuple[str, str]] = [
    ("cr_no", "CR number"),
    ("fir_no", "FIR number"),
    ("fir_year", "FIR year"),
    ("fir_date", "FIR date"),
    ("investigating_officer", "Investigating officer"),
    ("police_station", "Police station"),
    ("rank", "Rank"),
]

#: The Hearing fields the court owns. `state` and `source` are handled apart:
#: `state` is the one field a Snapshot always states rather than merely carries,
#: and `source` always becomes `court` once the court has spoken about a date.
HEARING_FIELDS = ("purpose", "outcome", "presiding_officer")


def _as_date(value: Any) -> Any:
    """Compare dates as dates. A Case stores two of them as timestamps."""
    if isinstance(value, dt.datetime):
        return value.date()
    return value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return _as_date(value).isoformat()
    return str(value)


@dataclass
class HearingPlan:
    """What this Snapshot would do to one date."""

    date: dt.date
    change: Literal["new", "changed", "superseded", "unchanged"]
    existing: Hearing | None
    #: The attribute values the Hearing should hold afterwards.
    values: dict[str, Any] = field(default_factory=dict)
    takes_over_firm_record: bool = False

    def face_after(self) -> HearingFaceOut:
        return HearingFaceOut(**self.values)

    def face_before(self) -> HearingFaceOut | None:
        if self.existing is None:
            return None
        return HearingFaceOut.model_validate(self.existing)


@dataclass
class RefreshPlan:
    """Everything applying this Snapshot to this Case would change.

    Empty of changes is a normal outcome, not a failure: most Refreshes of a
    quiet case find nothing has moved. Applying one still records that the Case
    was confirmed against DCMS today (CONTEXT.md, "Last Refreshed").
    """

    case: Case
    snapshot: DcmsSnapshot
    portal_case: PortalCase | None
    detail: PortalCaseDetail
    cino_mismatch: bool = False

    case_updates: dict[str, Any] = field(default_factory=dict)
    field_changes: list[FieldChangeOut] = field(default_factory=list)

    hearings: list[HearingPlan] = field(default_factory=list)
    firm_dates_not_reported: list[dt.date] = field(default_factory=list)

    #: `None` means the Snapshot never carried an Act & Section response at all,
    #: which is not the same as carrying an empty one - see ADR-0007 and
    #: `PortalCaseDetail.kinds_seen`.
    act_sections: "list[PortalActSection] | None" = None
    act_change: ListChangeOut | None = None

    crime_replace: bool = False
    crime_value: "PortalCrimeDetails | None" = None
    crime_changes: list[FieldChangeOut] = field(default_factory=list)

    counsel: list[tuple[CaseParty, list[PortalCounsel]]] = field(default_factory=list)
    counsel_changes: list[ListChangeOut] = field(default_factory=list)

    unlinked_parties: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.portal_case is not None

    @property
    def has_changes(self) -> bool:
        return bool(
            self.field_changes
            or [h for h in self.hearings if h.change != "unchanged"]
            or self.act_change
            or self.crime_changes
            or self.counsel_changes
        )


# ---------------------------------------------------------------------------
# Building the plan
# ---------------------------------------------------------------------------


def _read_snapshot(snapshot: DcmsSnapshot) -> tuple[PortalCase | None, PortalCaseDetail]:
    responses = split_responses(snapshot.raw_response) if snapshot.raw_response else []
    portal_case = extract_case(snapshot.parsed) if snapshot.parsed else None
    return portal_case, extract_case_detail(responses[1:])


def _plan_case_fields(plan: RefreshPlan) -> None:
    """The Case's own court-sourced columns.

    A value the portal did not report is left alone rather than cleared:
    absence is not a statement. The portal answering "no registration number
    yet" and the portal not mentioning one look identical here, and of the two
    readings only one can quietly destroy a label somebody is relying on.
    """
    portal_case = plan.portal_case
    assert portal_case is not None

    for attribute, label in CASE_FIELDS:
        new = getattr(portal_case, attribute)
        if new is None:
            continue
        old = getattr(plan.case, attribute)
        if _as_date(old) == _as_date(new):
            continue
        plan.case_updates[attribute] = new
        plan.field_changes.append(
            FieldChangeOut(field=attribute, label=label, before=_text(old), after=_text(new))
        )


def _merged_values(existing: Hearing | None, wanted: Hearing, orders_reported: bool) -> dict:
    """What a Hearing should read after the court has spoken about its date.

    Court-owned text the Snapshot does not carry is kept rather than blanked,
    for the same reason as the Case's own fields: a Snapshot whose follow-up
    burst was thin knows only that a date exists, and must not erase a purpose
    and an outcome an earlier, fuller Snapshot recorded.

    `order_available` moves only when this Snapshot actually carried the order
    response - otherwise a thin capture would report every order as gone.
    """
    values: dict[str, Any] = {
        "state": wanted.state,
        "source": HearingSource.court,
    }
    for attribute in HEARING_FIELDS:
        new = getattr(wanted, attribute)
        values[attribute] = new if new is not None else getattr(existing, attribute, None)

    if orders_reported:
        # `wanted` is detached, so an unmarked date reads `None` rather than the
        # column's default - the court reporting no order for it.
        values["order_available"] = bool(wanted.order_available)
    else:
        values["order_available"] = bool(getattr(existing, "order_available", False))
    return values


def _plan_hearings(plan: RefreshPlan, existing: list[Hearing]) -> None:
    portal_case = plan.portal_case
    assert portal_case is not None

    by_date = {h.date: h for h in existing}
    wanted = hearings_from_snapshot(portal_case, plan.detail)
    orders_reported = plan.detail.reported("orders")

    for row in sorted(wanted, key=lambda h: h.date):
        current = by_date.get(row.date)
        values = _merged_values(current, row, orders_reported)

        if current is None:
            plan.hearings.append(HearingPlan(date=row.date, change="new", existing=None, values=values))
            continue

        unchanged = all(getattr(current, key) == value for key, value in values.items())
        plan.hearings.append(
            HearingPlan(
                date=row.date,
                change="unchanged" if unchanged else "changed",
                existing=current,
                values=values,
                # The court's account standing over one the firm wrote down is
                # the one takeover ADR-0002 sanctions, and it is worth naming on
                # the screen rather than letting it happen quietly.
                takes_over_firm_record=(not unchanged and current.source is HearingSource.firm),
            )
        )

    reported = {row.date for row in wanted}
    for hearing in sorted(existing, key=lambda h: h.date):
        if hearing.date in reported or hearing.state is not HearingState.scheduled:
            continue
        if hearing.source is HearingSource.court:
            # The court said this date was coming and now says nothing about
            # it. That is what `superseded` is for.
            values = {
                "state": HearingState.superseded,
                "source": HearingSource.court,
                "purpose": hearing.purpose,
                "outcome": hearing.outcome,
                "presiding_officer": hearing.presiding_officer,
                "order_available": hearing.order_available,
            }
            plan.hearings.append(
                HearingPlan(
                    date=hearing.date, change="superseded", existing=hearing, values=values
                )
            )
        else:
            # A date an advocate heard announced in open court, which the
            # portal has not caught up with. Left exactly alone - this is the
            # disagreement ADR-0002 keeps the two sources apart for.
            plan.firm_dates_not_reported.append(hearing.date)


def _plan_act_sections(plan: RefreshPlan) -> None:
    if not plan.detail.reported("acts"):
        return

    plan.act_sections = list(plan.detail.act_sections)
    before = sorted(_act_label(a.act_name, a.section) for a in plan.case.act_sections)
    after = sorted(_act_label(a.name, a.section) for a in plan.act_sections)
    if before != after:
        plan.act_change = ListChangeOut(label="Act & Section", before=before, after=after)


def _act_label(name: str, section: str | None) -> str:
    return f"{name}/{section}" if section else name


def _plan_crime_details(plan: RefreshPlan) -> None:
    if not plan.detail.reported("crime"):
        return

    plan.crime_replace = True
    plan.crime_value = plan.detail.crime_details
    current = plan.case.crime_details

    for attribute, label in CRIME_FIELDS:
        old = getattr(current, attribute, None)
        new = getattr(plan.crime_value, attribute, None)
        if _as_date(old) == _as_date(new):
            continue
        plan.crime_changes.append(
            FieldChangeOut(
                field=attribute, label=f"Crime Details · {label}", before=_text(old), after=_text(new)
            )
        )


def _portal_individuals(portal_case: PortalCase) -> list[tuple[str, int, int]]:
    """Every individual the portal names, as (name, type, party_no).

    `type` 1 is the petitioner side and 2 the respondent side - the portal's own
    numbering, and the key its Counsel rows are filed under.
    """
    people: list[tuple[str, int, int]] = []
    for side, type_value in (("petitioner", 1), ("respondent", 2)):
        lead = getattr(portal_case, side)
        if lead is not None:
            people.append((lead.name, type_value, 0))
        for other in getattr(portal_case, f"{side}_others"):
            people.append((other.name, type_value, other.party_no))
    return people


def _plan_counsel(plan: RefreshPlan) -> None:
    """Counsel, matched to CaseParty rows by the portal's own recorded words.

    The match is on `portal_raw_name` - the string the portal used, stored
    verbatim beside the link when the Case was ingested - never on the Party
    name a person chose. Matching evidence to evidence is a lookup; matching a
    portal string to a human's chosen name would be the silent linking ADR-0005
    exists to forbid.

    A name with no CaseParty is reported and left. Creating one would mean
    inventing a Party, which only a person may do.
    """
    portal_case = plan.portal_case
    assert portal_case is not None

    by_raw_name: dict[str, CaseParty] = {
        p.portal_raw_name: p for p in plan.case.parties if p.portal_raw_name
    }

    for name, type_value, party_no in _portal_individuals(portal_case):
        case_party = by_raw_name.get(name)
        if case_party is None:
            plan.unlinked_parties.append(name)
            continue
        if not plan.detail.reported("counsel"):
            continue

        wanted = plan.detail.counsel_for(type_value, party_no)
        plan.counsel.append((case_party, wanted))

        before = sorted(c.name for c in case_party.counsels)
        after = sorted(c.name for c in wanted)
        if before != after:
            plan.counsel_changes.append(
                ListChangeOut(label=f"Counsel for {name}", before=before, after=after)
            )


async def build_plan(db: AsyncSession, case: Case, snapshot: DcmsSnapshot) -> RefreshPlan:
    """What applying this Snapshot to this Case would do, without doing any of it."""
    portal_case, detail = _read_snapshot(snapshot)
    plan = RefreshPlan(case=case, snapshot=snapshot, portal_case=portal_case, detail=detail)

    if portal_case is None:
        return plan

    if case.cino and portal_case.cino != case.cino:
        # A Refresh searches by CINO, so this can only mean the portal answered
        # about something else. Nothing is planned; the endpoint refuses to
        # apply it and the Snapshot is kept as the evidence that it happened.
        plan.cino_mismatch = True
        return plan

    hearings = list(
        (await db.execute(select(Hearing).where(Hearing.case_id == case.id).order_by(Hearing.date)))
        .unique()
        .scalars()
    )

    _plan_case_fields(plan)
    _plan_hearings(plan, hearings)
    _plan_act_sections(plan)
    _plan_crime_details(plan)
    _plan_counsel(plan)
    return plan


# ---------------------------------------------------------------------------
# Rendering it
# ---------------------------------------------------------------------------


def plan_to_diff(plan: RefreshPlan) -> RefreshDiffOut:
    raw = plan.snapshot.raw_response or ""
    return RefreshDiffOut(
        snapshot_id=plan.snapshot.id,
        case_id=plan.case.id,
        status=plan.snapshot.status,
        fetched_at=plan.snapshot.fetched_at,
        found=plan.found,
        cino=plan.portal_case.cino if plan.portal_case else None,
        cino_mismatch=plan.cino_mismatch,
        parse_error=plan.snapshot.parse_error,
        raw_preview=raw[:4000],
        fields=plan.field_changes,
        hearings=[
            HearingChangeOut(
                date=h.date,
                change=h.change,
                takes_over_firm_record=h.takes_over_firm_record,
                before=h.face_before(),
                after=h.face_after(),
            )
            for h in plan.hearings
            if h.change != "unchanged"
        ],
        act_sections=plan.act_change,
        crime_details=plan.crime_changes,
        counsel=plan.counsel_changes,
        unlinked_parties=plan.unlinked_parties,
        firm_dates_not_reported=plan.firm_dates_not_reported,
        has_changes=plan.has_changes,
    )


# ---------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------


def _decided(snapshot: DcmsSnapshot, advocate: Advocate, outcome: SnapshotStatus) -> None:
    snapshot.status = outcome
    snapshot.decided_at = dt.datetime.now(dt.timezone.utc)
    snapshot.decided_by_id = advocate.id


def _undecided_or_409(snapshot: DcmsSnapshot) -> None:
    if snapshot.status is not SnapshotStatus.captured:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This snapshot has already been {snapshot.status.value}.",
        )


async def apply_plan(db: AsyncSession, plan: RefreshPlan, advocate: Advocate) -> Case:
    """Take the Snapshot as the Case's official position, whole (rule 2).

    Nothing here is optional and nothing is per-field: this executes the plan
    the advocate was shown, in full, or it raises before touching anything.
    """
    snapshot = plan.snapshot
    _undecided_or_409(snapshot)

    if not plan.found:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This search found no case, so there is nothing to apply. Discard it instead.",
        )
    if plan.cino_mismatch:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The portal answered about {plan.portal_case.cino}, not this case's "
            f"{plan.case.cino}. It cannot be applied here.",
        )

    case = plan.case
    for attribute, value in plan.case_updates.items():
        setattr(case, attribute, value)

    for hearing_plan in plan.hearings:
        if hearing_plan.change == "unchanged":
            continue
        target = hearing_plan.existing
        if target is None:
            target = Hearing(case_id=case.id, date=hearing_plan.date)
            db.add(target)
        for attribute, value in hearing_plan.values.items():
            setattr(target, attribute, value)
        # Representation and who first noted the date are firm-authored and
        # survive the takeover untouched (ADR-0007).

    if plan.act_sections is not None:
        case.act_sections = [
            ActSection(case_id=case.id, act_code=a.code, act_name=a.name, section=a.section)
            for a in plan.act_sections
        ]

    if plan.crime_replace:
        crime = plan.crime_value
        case.crime_details = (
            None
            if crime is None
            else CrimeDetail(
                case_id=case.id,
                cr_no=crime.cr_no,
                fir_no=crime.fir_no,
                fir_year=crime.fir_year,
                fir_date=crime.fir_date,
                investigating_officer=crime.investigating_officer,
                police_station=crime.police_station,
                rank=crime.rank,
            )
        )

    for case_party, wanted in plan.counsel:
        # The outcome is exactly the Snapshot's list, as wholesale replacement
        # requires. Reconciling by name rather than clearing and re-inserting
        # only avoids a retained counsel colliding with itself on the unique
        # index within the one flush.
        by_name = {c.name: c for c in wanted}
        for existing in list(case_party.counsels):
            replacement = by_name.pop(existing.name, None)
            if replacement is None:
                case_party.counsels.remove(existing)
            else:
                existing.registration = replacement.registration
        for counsel in by_name.values():
            case_party.counsels.append(
                Counsel(
                    case_party_id=case_party.id,
                    name=counsel.name,
                    registration=counsel.registration,
                )
            )

    # The Case is confirmed as of when the court spoke, not as of when somebody
    # got round to pressing apply.
    case.last_refreshed_at = snapshot.fetched_at

    await _supersede_earlier(db, case.id, snapshot.id)
    snapshot.case_id = case.id
    _decided(snapshot, advocate, SnapshotStatus.applied)

    await db.commit()
    return await load_case(db, case.id)


async def _supersede_earlier(db: AsyncSession, case_id: uuid.UUID, keep: uuid.UUID) -> None:
    """Every previously applied Snapshot for this Case is now the older word.

    They are kept, of course - a Snapshot is never deleted (rule 3). This only
    says which one the Case currently stands on.
    """
    earlier = (
        await db.execute(
            select(DcmsSnapshot).where(
                DcmsSnapshot.case_id == case_id,
                DcmsSnapshot.status == SnapshotStatus.applied,
                DcmsSnapshot.id != keep,
            )
        )
    ).scalars()
    for snapshot in earlier:
        snapshot.status = SnapshotStatus.superseded


async def discard_snapshot(
    db: AsyncSession, snapshot: DcmsSnapshot, advocate: Advocate
) -> DcmsSnapshot:
    """The advocate judged it wrong. Kept, marked rejected, and applied to nothing.

    A rejected Snapshot is evidence, not rubbish: somebody paid a CAPTCHA for
    it and then decided the portal was wrong, which is worth being able to look
    back at (rule 3).
    """
    _undecided_or_409(snapshot)
    _decided(snapshot, advocate, SnapshotStatus.rejected)
    await db.commit()
    return snapshot
