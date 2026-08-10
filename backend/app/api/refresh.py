"""Refreshing one Case against DCMS.

The same act as Ingestion, into a Case that already exists (CONTEXT.md,
"Refresh"). Because the Court is already identified and the CINO already known,
the advocate chooses nothing: `start` walks the portal all the way to the
CAPTCHA in one call, and the only thing left is the one thing only a person may
do (ADR-0003).

Deciding is deliberately not tied to the live session. Ingestion's review has to
run inside its own session because the Court is completed from it; here the
Court is already complete, so a Snapshot can be looked at and applied long after
the browser has gone - which is what an advocate who was interrupted mid-refresh
needs.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentAdvocate, Db
from app.dcms import portal
from app.dcms.flight import join_responses, parse_flight
from app.dcms.session import SessionExpired, registry
from app.models import Case, DcmsSnapshot, SearchMode
from app.schemas import CaseDetail
from app.schemas.ingest import CaptchaOut, SubmitIn
from app.schemas.refresh import RefreshDiffOut, RefreshStartOut, SnapshotSummaryOut
from app.services.cases import load_case
from app.services.refresh import apply_plan, build_plan, discard_snapshot, plan_to_diff

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}", tags=["refresh"])


async def _case_or_404(db: Db, case_id: uuid.UUID) -> Case:
    case = await load_case(db, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


def _refreshable_or_409(case: Case) -> None:
    """Both halves of what a Refresh needs before it can begin.

    A provisional Court cannot be selected on the portal at all (CONTEXT.md,
    "Court"), and every search needs one before any tab becomes usable
    (ADR-0004). A Case with no CINO cannot be searched by CNR, and the raw
    `case_no` string the portal reports is not the shorthand its own Case No tab
    wants - see ROADMAP's open question on `reg_no`'s encoding. Both are stated
    plainly rather than guessed around.
    """
    if not case.court.is_complete:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{case.court.name} has not been identified on the DCMS portal yet, so it "
            "cannot be searched. Ingesting a case in this court identifies it.",
        )
    if not case.cino:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This case has no CINO yet, and a refresh searches by CNR. Find it on the "
            "portal by case or filing number first.",
        )


async def _session(session_id: str, advocate, case_id: uuid.UUID):
    try:
        session = await registry.get(session_id, advocate.id)
    except SessionExpired as exc:
        raise HTTPException(status.HTTP_410_GONE, str(exc)) from exc
    if session.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That refresh is for a different case")
    return session


def _portal_error(exc: portal.PortalError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.post("/refresh", response_model=RefreshStartOut)
async def start(case_id: uuid.UUID, db: Db, advocate: CurrentAdvocate) -> RefreshStartOut:
    """Open the portal on this Case and stop at the CAPTCHA.

    State, district and court come from the Court's own portal words, recorded
    verbatim when it was identified; the CNR tab is filled with the stored CINO.
    Everything is in place before the image is read, so the roughly thirty
    seconds the portal gives it starts with the advocate already looking.
    """
    case = await _case_or_404(db, case_id)
    _refreshable_or_409(case)

    session = await registry.open(advocate.id)
    session.case_id = case.id
    try:
        await portal.open_search(session.page)
        state, district, court = await portal.select_court(
            session.page,
            district=case.court.portal_district,
            court=case.court.portal_establishment,
            state=case.court.portal_state or portal.DEFAULT_STATE,
        )
        await portal.select_tab(session.page, SearchMode.cnr)
        await portal.fill_identifier(session.page, SearchMode.cnr, case.cino)
        captcha = await portal.captcha_image(session.page)
    except portal.PortalError as exc:
        await registry.close(session.id)
        raise _portal_error(exc) from exc

    session.state, session.district, session.court = state, district, court
    session.search_mode = SearchMode.cnr
    session.search_value = case.cino

    return RefreshStartOut(
        session_id=session.id,
        captcha=captcha,
        cino=case.cino,
        state=state,
        district=district,
        court=court,
    )


@router.get("/refresh/{session_id}/captcha", response_model=CaptchaOut)
async def reread_captcha(
    case_id: uuid.UUID, session_id: str, advocate: CurrentAdvocate
) -> CaptchaOut:
    """Re-read the CAPTCHA after it has rotated, without starting over."""
    session = await _session(session_id, advocate, case_id)
    try:
        return CaptchaOut(captcha=await portal.captcha_image(session.page))
    except portal.PortalError as exc:
        raise _portal_error(exc) from exc


@router.post("/refresh/{session_id}/submit", response_model=RefreshDiffOut)
async def submit(
    case_id: uuid.UUID, session_id: str, payload: SubmitIn, db: Db, advocate: CurrentAdvocate
) -> RefreshDiffOut:
    """Run the search, store the Snapshot, and say what applying it would do.

    The Snapshot is written before anything is read out of it, and it is
    attached to the Case from the moment it exists - unlike Ingestion, where
    there is no Case yet to attach it to. Nothing is applied here; that is a
    separate decision on a separate screen.
    """
    session = await _session(session_id, advocate, case_id)
    case = await _case_or_404(db, case_id)

    try:
        responses = await portal.submit(session.page, payload.captcha)
    except portal.PortalError as exc:
        raise _portal_error(exc) from exc

    raw = join_responses(responses)
    snapshot = DcmsSnapshot(
        case_id=case.id,
        court_id=case.court_id,
        search_mode=SearchMode.cnr,
        search_value=session.search_value,
        raw_response=raw,
        fetched_at=datetime.now(timezone.utc),
        fetched_by_id=advocate.id,
    )
    try:
        snapshot.parsed = parse_flight(responses[0]) if responses else None
    except Exception as exc:  # noqa: BLE001 - a bad parse must not lose the response
        snapshot.parse_error = f"{type(exc).__name__}: {exc}"
        log.exception("could not parse a DCMS response; raw kept on snapshot")

    db.add(snapshot)
    await db.commit()

    session.snapshot_id = snapshot.id
    # The browser has done its job. Deciding needs the Snapshot, not the session.
    await registry.close(session.id)

    plan = await build_plan(db, case, snapshot)
    return plan_to_diff(plan)


@router.delete("/refresh/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel(case_id: uuid.UUID, session_id: str, advocate: CurrentAdvocate) -> None:
    """Give up before submitting. The browser must not be left running."""
    try:
        await registry.get(session_id, advocate.id)
    except SessionExpired:
        return
    await registry.close(session_id)


# ---------------------------------------------------------------------------
# Deciding on a Snapshot, with or without a live session
# ---------------------------------------------------------------------------


@router.get("/snapshots", response_model=list[SnapshotSummaryOut])
async def list_snapshots(
    case_id: uuid.UUID, db: Db, _: CurrentAdvocate
) -> list[DcmsSnapshot]:
    """Every Snapshot ever taken for this Case, newest first.

    Including the rejected ones. Somebody paid a CAPTCHA for each (rule 3).
    """
    result = await db.execute(
        select(DcmsSnapshot)
        .where(DcmsSnapshot.case_id == case_id)
        .order_by(DcmsSnapshot.fetched_at.desc())
    )
    return list(result.unique().scalars())


async def _snapshot_or_404(db: Db, case_id: uuid.UUID, snapshot_id: uuid.UUID) -> DcmsSnapshot:
    snapshot = await db.get(DcmsSnapshot, snapshot_id)
    if snapshot is None or snapshot.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Snapshot not found")
    return snapshot


@router.get("/snapshots/{snapshot_id}/diff", response_model=RefreshDiffOut)
async def diff(
    case_id: uuid.UUID, snapshot_id: uuid.UUID, db: Db, _: CurrentAdvocate
) -> RefreshDiffOut:
    """What applying this Snapshot would do, worked out against the Case as it
    stands right now - not as it stood when the search ran."""
    case = await _case_or_404(db, case_id)
    snapshot = await _snapshot_or_404(db, case_id, snapshot_id)
    return plan_to_diff(await build_plan(db, case, snapshot))


@router.post("/snapshots/{snapshot_id}/apply", response_model=CaseDetail)
async def apply(
    case_id: uuid.UUID, snapshot_id: uuid.UUID, db: Db, advocate: CurrentAdvocate
) -> Case:
    """Take this Snapshot as the Case's official position, whole (rule 2).

    Recomputed from the Case's current state rather than trusting a diff the
    browser is holding, so two advocates deciding at once cannot apply a plan
    that stopped being true.
    """
    case = await _case_or_404(db, case_id)
    snapshot = await _snapshot_or_404(db, case_id, snapshot_id)
    plan = await build_plan(db, case, snapshot)
    return await apply_plan(db, plan, advocate)


@router.post("/snapshots/{snapshot_id}/discard", response_model=SnapshotSummaryOut)
async def discard(
    case_id: uuid.UUID, snapshot_id: uuid.UUID, db: Db, advocate: CurrentAdvocate
) -> DcmsSnapshot:
    """Judge the Snapshot wrong and keep it anyway, marked rejected."""
    await _case_or_404(db, case_id)
    snapshot = await _snapshot_or_404(db, case_id, snapshot_id)
    return await discard_snapshot(db, snapshot, advocate)
