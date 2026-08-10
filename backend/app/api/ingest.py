"""The ingestion wizard's back end.

One live portal session per in-flight ingestion. The advocate walks it: district
→ court → identifier → CAPTCHA → search. Ingestion is the same mechanism as a
Refresh, only into a Case that does not exist yet (ADR-0005).

A person solves the CAPTCHA every time. Nothing here reads or interprets it.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentAdvocate, Db
from app.dcms import portal
from app.dcms.flight import extract_case, join_responses, parse_flight
from app.dcms.session import SessionExpired, registry
from app.models import Case, Court, DcmsSnapshot, SearchMode, SnapshotStatus
from app.schemas import CaseDetail
from app.schemas.ingest import (
    CaptchaOut,
    ChooseCourtIn,
    ChooseCourtOut,
    ChooseDistrictIn,
    ChooseDistrictOut,
    IdentifierIn,
    ReviewIn,
    StartOut,
    SubmitIn,
    SubmitOut,
)
from app.services.ingest import create_case_from_snapshot

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


async def _session(session_id: str, advocate):
    try:
        return await registry.get(session_id, advocate.id)
    except SessionExpired as exc:
        raise HTTPException(status.HTTP_410_GONE, str(exc)) from exc


def _portal_error(exc: portal.PortalError) -> HTTPException:
    # The portal is often briefly unavailable. Say so plainly rather than
    # leaking a stack trace at an advocate.
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.post("/start", response_model=StartOut)
async def start(advocate: CurrentAdvocate) -> StartOut:
    """Open a browser on the portal and read its district list."""
    session = await registry.open(advocate.id)
    try:
        await portal.open_search(session.page)
        districts = await portal.list_options(session.page, portal.DISTRICT_PLACEHOLDER)
    except portal.PortalError as exc:
        await registry.close(session.id)
        raise _portal_error(exc) from exc

    return StartOut(session_id=session.id, districts=districts)


@router.post("/{session_id}/district", response_model=ChooseDistrictOut)
async def choose_district(
    session_id: str, payload: ChooseDistrictIn, advocate: CurrentAdvocate
) -> ChooseDistrictOut:
    session = await _session(session_id, advocate)
    try:
        session.district = await portal._choose(
            session.page, portal.DISTRICT_PLACEHOLDER, payload.district
        )
        courts = await portal.list_options(session.page, portal.COURT_PLACEHOLDER)
    except portal.PortalError as exc:
        raise _portal_error(exc) from exc
    return ChooseDistrictOut(courts=courts)


@router.post("/{session_id}/court", response_model=ChooseCourtOut)
async def choose_court(
    session_id: str, payload: ChooseCourtIn, db: Db, advocate: CurrentAdvocate
) -> ChooseCourtOut:
    """Choose the establishment, and find out what case types it offers.

    Until this is done the portal will not run any search at all — not even by
    CNR (ADR-0004).
    """
    session = await _session(session_id, advocate)
    if not session.district:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a district first")

    try:
        session.court = await portal._choose(
            session.page, portal.COURT_PLACEHOLDER, payload.court
        )
        session.state = portal.DEFAULT_STATE
        case_types = await portal.case_types(session.page)
    except portal.PortalError as exc:
        raise _portal_error(exc) from exc

    # Do we already know this establishment? If so the Case will attach to the
    # existing Court rather than making a second one.
    known = (
        await db.execute(
            select(Court).where(
                Court.portal_district == session.district,
                Court.portal_establishment == session.court,
            )
        )
    ).scalar_one_or_none()

    return ChooseCourtOut(
        state=session.state,
        district=session.district,
        court=session.court,
        case_types=case_types,
        known_court_id=known.id if known else None,
        known_court_name=known.name if known else None,
    )


@router.post("/{session_id}/identifier", response_model=CaptchaOut)
async def fill_identifier(
    session_id: str, payload: IdentifierIn, db: Db, advocate: CurrentAdvocate
) -> CaptchaOut:
    """Fill in the identifier and hand back the CAPTCHA for a person to read.

    Everything else is filled first, so the roughly thirty seconds the portal
    gives the CAPTCHA starts with the advocate already looking at it (ADR-0004).
    """
    session = await _session(session_id, advocate)
    if not session.court:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a court first")

    value = payload.value.strip()

    # Searching by CNR means the identifier *is* the CINO, so a duplicate can be
    # spotted before the advocate spends a CAPTCHA on it.
    duplicate = None
    if payload.mode is SearchMode.cnr:
        duplicate = (
            await db.execute(select(Case.id).where(Case.cino == value))
        ).scalar_one_or_none()

    try:
        await portal.select_tab(session.page, payload.mode)
        await portal.fill_identifier(
            session.page,
            payload.mode,
            value,
            case_type=payload.case_type,
            year=payload.year,
        )
        captcha = await portal.captcha_image(session.page)
    except portal.PortalError as exc:
        raise _portal_error(exc) from exc

    session.search_mode = payload.mode
    session.search_value = value
    session.search_case_type = payload.case_type
    session.search_year = payload.year
    return CaptchaOut(captcha=captcha, duplicate_case_id=duplicate)


@router.get("/{session_id}/captcha", response_model=CaptchaOut)
async def reread_captcha(session_id: str, advocate: CurrentAdvocate) -> CaptchaOut:
    """Re-read the CAPTCHA after it has rotated, without starting over."""
    session = await _session(session_id, advocate)
    try:
        return CaptchaOut(captcha=await portal.captcha_image(session.page))
    except portal.PortalError as exc:
        raise _portal_error(exc) from exc


@router.post("/{session_id}/submit", response_model=SubmitOut)
async def submit(
    session_id: str, payload: SubmitIn, db: Db, advocate: CurrentAdvocate
) -> SubmitOut:
    """Submit the search and store whatever comes back.

    The Snapshot is written before anything is parsed out of it. A parse failure
    must leave evidence, not nothing — the advocate paid a CAPTCHA for this.
    """
    session = await _session(session_id, advocate)
    mode = getattr(session, "search_mode", None)
    if mode is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fill in an identifier first")

    try:
        responses = await portal.submit(session.page, payload.captcha)
    except portal.PortalError as exc:
        raise _portal_error(exc) from exc

    # A found case's detail view arrives as several responses, not one - all of
    # them are kept on the Snapshot (rule 3), even though only the first is
    # parsed below. `extract_case` and the review screen read only the search
    # result row for now; the rest (case history, acts & section, crime
    # details) is captured but not yet parsed - see ROADMAP.md.
    raw = join_responses(responses)

    court = None
    if session.district and session.court:
        court = (
            await db.execute(
                select(Court).where(
                    Court.portal_district == session.district,
                    Court.portal_establishment == session.court,
                )
            )
        ).scalar_one_or_none()

    snapshot = DcmsSnapshot(
        court_id=court.id if court else None,
        search_mode=mode,
        search_value=session.search_value,
        search_case_type=session.search_case_type,
        search_year=session.search_year,
        raw_response=raw,
        fetched_at=datetime.now(timezone.utc),
        fetched_by_id=advocate.id,
    )

    try:
        snapshot.parsed = parse_flight(responses[0])
    except Exception as exc:  # noqa: BLE001 - a bad parse must not lose the response
        snapshot.parse_error = f"{type(exc).__name__}: {exc}"
        log.exception("could not parse a DCMS response; raw kept on snapshot")

    db.add(snapshot)
    await db.commit()

    session.snapshot_id = snapshot.id

    return SubmitOut(
        snapshot_id=snapshot.id,
        raw_length=len(raw),
        raw_preview=raw[:4000],
        parsed=snapshot.parsed,
        parse_error=snapshot.parse_error,
        extracted=extract_case(snapshot.parsed) if snapshot.parsed else None,
    )


@router.post("/{session_id}/review", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
async def review(
    session_id: str, payload: ReviewIn, db: Db, advocate: CurrentAdvocate
) -> Case:
    """Create the Case from a reviewed Snapshot, and apply it.

    The Snapshot is applied whole, as a matter of course - there is nothing yet
    to compare it against. Only what the portal cannot know comes from
    `payload`: which side is ours, which Advocate holds which role, and Firm
    Status (ADR-0005).
    """
    session = await _session(session_id, advocate)
    if session.snapshot_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Submit a search first")

    snapshot = await db.get(DcmsSnapshot, session.snapshot_id)
    if snapshot is None or snapshot.status is not SnapshotStatus.captured:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to review")

    portal_case = extract_case(snapshot.parsed) if snapshot.parsed else None
    if portal_case is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This search found no case to create from")

    for side in ("petitioner", "respondent"):
        if getattr(portal_case, side) is not None and getattr(payload, side) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Link or create a Party for the {side}")

        others_key = f"{side}_others"
        wanted = len(getattr(portal_case, others_key))
        given = len(getattr(payload, others_key))
        if given != wanted:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"The portal reported {wanted} more {side}(s) beyond the lead name - "
                f"link or create a Party for each of them ({given} given)",
            )
    if getattr(portal_case, payload.client_side) is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"The portal did not return a {payload.client_side}"
        )

    case = await create_case_from_snapshot(db, session, snapshot, portal_case, payload, advocate)
    await registry.close(session.id)
    return case


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel(session_id: str, advocate: CurrentAdvocate) -> None:
    """Give up on an ingestion. The browser must not be left running."""
    try:
        await registry.get(session_id, advocate.id)
    except SessionExpired:
        return
    await registry.close(session_id)
