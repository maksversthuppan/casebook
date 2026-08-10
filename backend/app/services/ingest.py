"""Turning a reviewed DCMS Snapshot into a Case.

The Snapshot's own fields are applied whole, as a matter of course - there is
nothing yet to compare them against (CONTEXT.md, "Applying a Snapshot"). Only
what the portal cannot know - which side is ours, which Advocate holds which
role, and Firm Status - comes from the person reviewing it (ADR-0005).
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dcms.flight import PortalCase, PortalCaseDetail, extract_case_detail, split_responses
from app.dcms.session import PortalSession
from app.models import (
    ActSection,
    Advocate,
    Assignment,
    Case,
    CaseParty,
    Counsel,
    Court,
    CrimeDetail,
    DcmsSnapshot,
    Hearing,
)
from app.models.enums import HearingSource, HearingState, PartyRole, SnapshotStatus
from app.schemas.ingest import ReviewIn
from app.services.cases import (
    _advocates_exist,
    _check_unique_advocates,
    _resolve_party,
    load_case,
    record_firm_status,
)


async def _resolve_ingested_court(db: AsyncSession, session: PortalSession) -> Court:
    """The Court the session searched in, completed with the portal's own words.

    A Court already known by this district and establishment is reused; a new
    one is created complete rather than provisional, since it is being made
    from exactly what the portal's own dropdowns offered, not typed by hand.
    This is the moment ADR-0005 refers to as how a Court becomes complete.
    """
    existing = (
        await db.execute(
            select(Court).where(
                Court.portal_district == session.district,
                Court.portal_establishment == session.court,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    court = Court(
        name=session.court,
        portal_state=session.state,
        portal_district=session.district,
        portal_establishment=session.court,
    )
    db.add(court)
    await db.flush()
    return court


def hearings_from_snapshot(
    portal_case: PortalCase, case_detail: PortalCaseDetail
) -> list[Hearing]:
    """Every Hearing this Snapshot can account for.

    Detached `Hearing` objects, describing what the court says about each date
    rather than rows to be added as they stand - Ingestion adds them, a Refresh
    merges them onto whatever the Case already holds for those dates
    (`services/refresh.py`).

    The rich case-history burst (see ROADMAP.md, 2026-08-09) carries the whole
    timeline, each row with its own presiding officer, purpose and outcome -
    use it when present. A Case with no history yet (nothing to report before
    the first listing, or a burst that came back thin) falls back to the old
    next/last-only behaviour, which is all the bare search response can offer.

    `first_hearing` (the thin response's own field) is still left out even in
    the fallback path - it has so far always equalled the filing/registration
    date exactly (ROADMAP Findings, 2026-08-09), reading as the case's
    registration rather than a listing before the court.
    """
    by_date: dict = {}

    for row in case_detail.hearings:
        by_date[row.date] = Hearing(
            date=row.date,
            state=HearingState.held,
            source=HearingSource.court,
            purpose=row.purpose,
            outcome=row.outcome,
            presiding_officer=row.presiding_officer,
        )

    if case_detail.hearings:
        latest = case_detail.hearings[-1]
        if latest.next_date is not None and latest.next_date not in by_date:
            by_date[latest.next_date] = Hearing(
                date=latest.next_date, state=HearingState.scheduled, source=HearingSource.court
            )
    else:
        if portal_case.next_hearing is not None:
            by_date[portal_case.next_hearing] = Hearing(
                date=portal_case.next_hearing,
                state=HearingState.scheduled,
                source=HearingSource.court,
            )
        if portal_case.last_hearing is not None and portal_case.last_hearing not in by_date:
            by_date[portal_case.last_hearing] = Hearing(
                date=portal_case.last_hearing, state=HearingState.held, source=HearingSource.court
            )

    for order_date in case_detail.order_dates:
        if order_date in by_date:
            by_date[order_date].order_available = True

    return list(by_date.values())


async def create_case_from_snapshot(
    db: AsyncSession,
    session: PortalSession,
    snapshot: DcmsSnapshot,
    portal_case: PortalCase,
    payload: ReviewIn,
    advocate: Advocate,
) -> Case:
    if snapshot.status is not SnapshotStatus.captured:
        raise HTTPException(status.HTTP_409_CONFLICT, "This Snapshot has already been decided")

    advocate_ids = [a.advocate_id for a in payload.assignments]
    _check_unique_advocates(payload.assignments)
    await _advocates_exist(db, advocate_ids)

    court = await _resolve_ingested_court(db, session)
    # The main search result is responses[0], already read into portal_case;
    # everything else - case history, acts & section, crime details, the other
    # side's counsel, order dates - lives in the rest of the burst (ROADMAP.md,
    # 2026-08-09).
    responses = split_responses(snapshot.raw_response) if snapshot.raw_response else []
    case_detail = extract_case_detail(responses[1:])

    case = Case(
        court_id=court.id,
        cino=portal_case.cino,
        case_type=portal_case.case_type,
        registration_number=portal_case.registration_number,
        registration_date=portal_case.registration_date,
        filing_number=portal_case.filing_number,
        filing_date=portal_case.filing_date,
        court_status=portal_case.court_status,
        firm_status=payload.firm_status,
        last_refreshed_at=datetime.now(timezone.utc),
        created_by_id=advocate.id,
    )
    db.add(case)

    try:
        await db.flush()

        # 1 = petitioner side, 2 = respondent side - the portal's own type
        # values, and the first half of the key `case_detail.counsel_for` uses.
        type_for_side = {"petitioner": 1, "respondent": 2}

        for side in ("petitioner", "respondent"):
            lead = getattr(portal_case, side)
            if lead is None:
                continue
            role = PartyRole.client if side == payload.client_side else PartyRole.opposite_party
            type_value = type_for_side[side]

            individuals = [lead, *getattr(portal_case, f"{side}_others")]
            specs = [getattr(payload, side), *getattr(payload, f"{side}_others")]
            if len(specs) != len(individuals):
                # The API layer checks this already; re-checked here too, so a
                # caller that skips it (as the direct-service-call tests do)
                # cannot silently zip past the ones with no review spec.
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Every {side} the portal enumerated needs a Party spec "
                    f"({len(individuals)} individuals, {len(specs)} given)",
                )

            for position, (portal_party, spec) in enumerate(zip(individuals, specs), start=1):
                party = await _resolve_party(db, spec)
                case_party = CaseParty(
                    id=uuid.uuid4(),
                    case_id=case.id,
                    party_id=party.id,
                    role=role,
                    position=position,
                    portal_raw_name=portal_party.name,
                )
                db.add(case_party)
                for counsel in case_detail.counsel_for(type_value, portal_party.party_no):
                    db.add(
                        Counsel(
                            case_party_id=case_party.id,
                            name=counsel.name,
                            registration=counsel.registration,
                        )
                    )

        for spec in payload.assignments:
            db.add(Assignment(case_id=case.id, advocate_id=spec.advocate_id, role=spec.role))

        # Ingestion sets a Firm Status too, so it opens a history the same way
        # manual creation does - otherwise every ingested Case would have a
        # status with no record of where it came from.
        record_firm_status(
            db,
            case.id,
            from_status=None,
            to_status=payload.firm_status,
            changed_by=advocate,
        )

        for hearing in hearings_from_snapshot(portal_case, case_detail):
            hearing.case_id = case.id
            db.add(hearing)

        if case_detail.crime_details is not None:
            crime = case_detail.crime_details
            db.add(
                CrimeDetail(
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

        for act in case_detail.act_sections:
            db.add(
                ActSection(case_id=case.id, act_code=act.code, act_name=act.name, section=act.section)
            )

        snapshot.case_id = case.id
        snapshot.status = SnapshotStatus.applied
        snapshot.decided_at = datetime.now(timezone.utc)
        snapshot.decided_by_id = advocate.id

        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "cases_cino_key" in str(exc.orig):
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"A case with CINO {portal_case.cino} already exists"
            ) from exc
        raise

    return await load_case(db, case.id)
