"""Applying a later Snapshot to a Case that already exists (ADR-0007).

The two real captures are used as a genuine before-and-after: a Case is
ingested from `dcms_case_found.txt`, which is the search response alone and so
knows only two dates and nothing else, and then refreshed with
`dcms_case_detail_burst.txt`, the whole burst for the same case. That is an
honest refresh - same case, more of the court's account - and it exercises
every block a Refresh writes without anyone hand-editing a payload into a shape
the portal has never actually produced.

The portal itself is never touched here. `start` and `submit` need a live
browser and a person reading a CAPTCHA; everything after them does not, which
is the point of deciding being untied from the session.
"""

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.dcms.flight import extract_case, parse_flight, split_responses
from app.models import (
    Case,
    DcmsSnapshot,
    DiaryEntry,
    Hearing,
    HearingSource,
    HearingState,
    SnapshotStatus,
)
from app.schemas.ingest import ReviewIn, ReviewPartyIn
from app.services.cases import load_case
from app.services.ingest import create_case_from_snapshot
from app.services.refresh import apply_plan, build_plan, discard_snapshot, plan_to_diff

FIXTURES = Path(__file__).parent / "fixtures"

CINO = "KLTV080027432025"
#: The first date in this case's real history, and the one the firm is given a
#: record of below so the court has something to take over.
FIRST_HISTORY_DATE = dt.date(2025, 5, 29)


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture
def session():
    """Stands in for a live `PortalSession` - only these three fields are used."""
    return SimpleNamespace(
        state="KERALA",
        district="THIRUVANANTHAPURAM",
        court="Addl. Chief Judicial Magistrate Court, Thiruvananthapuram",
    )


async def _snapshot(db, fixture: str, *, case_id=None) -> DcmsSnapshot:
    raw = _load(fixture)
    snapshot = DcmsSnapshot(
        case_id=case_id,
        search_mode="cnr",
        search_value=CINO,
        raw_response=raw,
        parsed=parse_flight(split_responses(raw)[0]),
        fetched_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def _ingest(db, session, advocates, fixture: str) -> Case:
    """A Case as Ingestion leaves it, from one of the two real captures."""
    snapshot = await _snapshot(db, fixture)
    portal_case = extract_case(snapshot.parsed)
    payload = ReviewIn(
        client_side="petitioner",
        petitioner=ReviewPartyIn(new_party={"name": "Rekha Devi P S and 2 Others"}),
        respondent=ReviewPartyIn(new_party={"name": "BINU S L and ANOTHER"}),
        petitioner_others=[
            ReviewPartyIn(new_party={"name": "Diya R Binu"}),
            ReviewPartyIn(new_party={"name": "Nila R Binu"}),
        ],
        respondent_others=[ReviewPartyIn(new_party={"name": "Leela R"})],
        assignments=[{"advocate_id": advocates["anil"].id, "role": "lead"}],
    )
    return await create_case_from_snapshot(
        db, session, snapshot, portal_case, payload, advocates["anil"]
    )


async def _refresh(db, case: Case, advocates, fixture: str = "dcms_case_detail_burst.txt"):
    """Capture a later Snapshot for an existing Case and plan it."""
    snapshot = await _snapshot(db, fixture, case_id=case.id)
    await db.commit()
    fresh = await load_case(db, case.id)
    return snapshot, await build_plan(db, fresh, snapshot)


async def _hearings(db, case_id) -> dict[dt.date, Hearing]:
    rows = (
        (await db.execute(select(Hearing).where(Hearing.case_id == case_id))).unique().scalars()
    )
    return {h.date: h for h in rows}


class TestDiff:
    """What the screen shows is worked out from the Case as it stands."""

    async def test_the_burst_is_a_real_change_over_the_bare_search_response(
        self, db, session, advocates
    ):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        _, plan = await _refresh(db, case, advocates)
        diff = plan_to_diff(plan)

        assert diff.found is True
        assert diff.cino == CINO
        assert diff.has_changes is True

        # The bare response knew two dates. The burst reports eleven: ten real
        # hearings from the history plus the date the last of them adjourned
        # to, which is the one the bare response already had and which nothing
        # about has changed.
        by_change: dict[str, set[dt.date]] = {}
        for change in diff.hearings:
            by_change.setdefault(change.change, set()).add(change.date)
        assert len(by_change["new"]) == 9
        # The one date both knew, now with the court's account of it attached.
        assert by_change["changed"] == {dt.date(2026, 8, 7)}
        assert dt.date(2026, 10, 1) not in {c.date for c in diff.hearings}

        assert diff.act_sections is not None
        assert diff.act_sections.before == []
        assert [c.label for c in diff.crime_details] == ["Crime Details · Police station"]
        assert any("BINU S L and ANOTHER" in c.label for c in diff.counsel)

    async def test_court_status_unchanged_is_not_reported_as_a_change(
        self, db, session, advocates
    ):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        _, plan = await _refresh(db, case, advocates)
        assert "court_status" not in {f.field for f in plan_to_diff(plan).fields}

    async def test_the_same_snapshot_again_changes_nothing(self, db, session, advocates):
        """A refresh of a case nothing has happened to is the common outcome,
        and must read as such rather than as a pile of no-op edits."""
        case = await _ingest(db, session, advocates, "dcms_case_detail_burst.txt")
        _, plan = await _refresh(db, case, advocates)
        diff = plan_to_diff(plan)

        assert diff.has_changes is False
        assert diff.fields == []
        assert diff.hearings == []
        assert diff.act_sections is None
        assert diff.crime_details == []
        assert diff.counsel == []

    async def test_a_firm_recorded_date_the_court_reports_is_flagged_as_a_takeover(
        self, db, session, advocates
    ):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        db.add(
            Hearing(
                case_id=case.id,
                date=FIRST_HISTORY_DATE,
                state=HearingState.scheduled,
                source=HearingSource.firm,
                purpose="What the advocate wrote down",
                recorded_by_id=advocates["anil"].id,
            )
        )
        await db.commit()

        _, plan = await _refresh(db, case, advocates)
        change = next(h for h in plan_to_diff(plan).hearings if h.date == FIRST_HISTORY_DATE)

        assert change.change == "changed"
        assert change.takes_over_firm_record is True
        assert change.before.purpose == "What the advocate wrote down"
        assert change.after.source == HearingSource.court
        assert change.after.presiding_officer == "Smt.Elsa Catherine George"

    async def test_a_firm_date_the_court_says_nothing_about_is_reported_not_touched(
        self, db, session, advocates
    ):
        """The judge announced a date the portal has not caught up with. That
        disagreement is the reason ADR-0002 keeps the two sources apart."""
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        announced = dt.date(2027, 3, 4)
        db.add(
            Hearing(
                case_id=case.id,
                date=announced,
                state=HearingState.scheduled,
                source=HearingSource.firm,
                recorded_by_id=advocates["anil"].id,
            )
        )
        await db.commit()

        _, plan = await _refresh(db, case, advocates)
        diff = plan_to_diff(plan)

        assert diff.firm_dates_not_reported == [announced]
        assert announced not in {h.date for h in diff.hearings}

    async def test_a_court_date_the_court_stops_reporting_is_superseded(
        self, db, session, advocates
    ):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        stale = dt.date(2026, 12, 25)
        db.add(
            Hearing(
                case_id=case.id,
                date=stale,
                state=HearingState.scheduled,
                source=HearingSource.court,
            )
        )
        await db.commit()

        _, plan = await _refresh(db, case, advocates)
        change = next(h for h in plan_to_diff(plan).hearings if h.date == stale)
        assert change.change == "superseded"
        assert change.after.state == HearingState.superseded

    async def test_an_unlinked_name_is_reported_never_linked(self, db, session, advocates):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        fresh = await load_case(db, case.id)
        # As though somebody had unlinked this party by hand: the portal still
        # names them, and nothing about a Refresh may re-link them (ADR-0005).
        target = next(p for p in fresh.parties if p.portal_raw_name == "Leela R")
        target.portal_raw_name = None
        await db.commit()

        _, plan = await _refresh(db, case, advocates)
        assert plan_to_diff(plan).unlinked_parties == ["Leela R"]

    async def test_a_response_about_another_case_is_refused(self, db, session, advocates):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        fresh = await load_case(db, case.id)
        fresh.cino = "KLTV080099999999"
        await db.commit()

        snapshot, plan = await _refresh(db, case, advocates)
        diff = plan_to_diff(plan)
        assert diff.cino_mismatch is True
        assert diff.hearings == []

        with pytest.raises(HTTPException) as exc:
            await apply_plan(db, plan, advocates["anil"])
        assert exc.value.status_code == 409
        assert snapshot.status == SnapshotStatus.captured


class TestApply:
    async def test_the_whole_court_account_lands(self, db, session, advocates):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        snapshot, plan = await _refresh(db, case, advocates)
        applied = await apply_plan(db, plan, advocates["anil"])

        assert len(await _hearings(db, case.id)) == 11
        assert len(applied.act_sections) == 1
        assert applied.crime_details is not None
        by_name = {p.portal_raw_name: p for p in applied.parties}
        assert {c.name for c in by_name["BINU S L and ANOTHER"].counsels} == {
            "AJITH R",
            "ASHEER A K",
        }
        assert applied.last_refreshed_at == snapshot.fetched_at
        assert snapshot.status == SnapshotStatus.applied
        assert snapshot.decided_by_id == advocates["anil"].id

    async def test_the_court_version_stands_over_a_firm_record(self, db, session, advocates):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        db.add(
            Hearing(
                case_id=case.id,
                date=FIRST_HISTORY_DATE,
                state=HearingState.scheduled,
                source=HearingSource.firm,
                purpose="What the advocate wrote down",
                recorded_by_id=advocates["anil"].id,
                represented_by_advocate_id=advocates["priya"].id,
            )
        )
        await db.commit()

        _, plan = await _refresh(db, case, advocates)
        await apply_plan(db, plan, advocates["anil"])

        taken_over = (await _hearings(db, case.id))[FIRST_HISTORY_DATE]
        assert taken_over.source is HearingSource.court
        assert taken_over.state is HearingState.held
        assert taken_over.presiding_officer == "Smt.Elsa Catherine George"
        # Firm-authored either side of the takeover, and untouched by it
        # (ADR-0007): who is on record for the date, and who first noted it.
        assert taken_over.represented_by_advocate_id == advocates["priya"].id
        assert taken_over.recorded_by_id == advocates["anil"].id

    async def test_authored_content_and_the_firms_own_view_survive(
        self, db, session, advocates
    ):
        """The load-bearing half of ADR-0002: a refresh has no reach into
        anything a person composed or decided."""
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        fresh = await load_case(db, case.id)
        fresh.firm_status = "on_hold"
        db.add(
            DiaryEntry(
                case_id=case.id,
                date=FIRST_HISTORY_DATE,
                author_id=advocates["anil"].id,
                body="Client called; wants the matter settled.",
            )
        )
        await db.commit()

        _, plan = await _refresh(db, case, advocates)
        applied = await apply_plan(db, plan, advocates["anil"])

        assert applied.firm_status == "on_hold"
        entry = (
            (await db.execute(select(DiaryEntry).where(DiaryEntry.case_id == case.id)))
            .unique()
            .scalars()
            .one()
        )
        assert entry.body == "Client called; wants the matter settled."

    async def test_a_thin_snapshot_does_not_wipe_what_a_fuller_one_recorded(
        self, db, session, advocates
    ):
        """A Snapshot whose burst never arrived says nothing about acts or
        crime details. Saying nothing is not saying none (ADR-0007)."""
        case = await _ingest(db, session, advocates, "dcms_case_detail_burst.txt")
        _, plan = await _refresh(db, case, advocates, "dcms_case_found.txt")
        applied = await apply_plan(db, plan, advocates["anil"])

        assert len(applied.act_sections) == 1
        assert applied.crime_details is not None
        by_name = {p.portal_raw_name: p for p in applied.parties}
        assert len(by_name["BINU S L and ANOTHER"].counsels) == 2
        # Nor does it blank the court's own words on a date it knows only the
        # existence of.
        assert (await _hearings(db, case.id))[FIRST_HISTORY_DATE].presiding_officer

    async def test_the_earlier_applied_snapshot_becomes_superseded(
        self, db, session, advocates
    ):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        first = (
            (await db.execute(select(DcmsSnapshot).where(DcmsSnapshot.case_id == case.id)))
            .unique()
            .scalars()
            .one()
        )
        assert first.status == SnapshotStatus.applied

        _, plan = await _refresh(db, case, advocates)
        await apply_plan(db, plan, advocates["anil"])

        await db.refresh(first)
        assert first.status == SnapshotStatus.superseded

    async def test_a_snapshot_is_decided_once(self, db, session, advocates):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        snapshot, plan = await _refresh(db, case, advocates)
        await apply_plan(db, plan, advocates["anil"])

        fresh = await load_case(db, case.id)
        with pytest.raises(HTTPException) as exc:
            await apply_plan(db, await build_plan(db, fresh, snapshot), advocates["anil"])
        assert exc.value.status_code == 409


class TestDiscard:
    async def test_a_rejected_snapshot_is_kept_and_changes_nothing(
        self, db, session, advocates
    ):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        before = len(await _hearings(db, case.id))

        snapshot, _ = await _refresh(db, case, advocates)
        await discard_snapshot(db, snapshot, advocates["priya"])

        assert snapshot.status == SnapshotStatus.rejected
        assert snapshot.decided_by_id == advocates["priya"].id
        assert snapshot.raw_response
        assert len(await _hearings(db, case.id)) == before

    async def test_a_discarded_snapshot_cannot_then_be_applied(self, db, session, advocates):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        snapshot, plan = await _refresh(db, case, advocates)
        await discard_snapshot(db, snapshot, advocates["priya"])

        with pytest.raises(HTTPException) as exc:
            await apply_plan(db, plan, advocates["anil"])
        assert exc.value.status_code == 409


class TestRefreshableGuards:
    """Both refuse before a browser is ever opened, which is what makes them
    worth stating: no CAPTCHA is spent finding out."""

    async def test_a_case_with_no_cino_cannot_be_refreshed(self, signed_in, db, advocates):
        r = await signed_in.post(
            "/api/cases",
            json={
                "new_court_name": "Munsiff Court Ernakulam",
                "parties": [{"new_party": {"name": "A Client"}, "role": "client"}],
                "assignments": [{"advocate_id": str(advocates["anil"].id), "role": "lead"}],
            },
        )
        assert r.status_code == 201, r.text
        case_id = r.json()["id"]

        r = await signed_in.post(f"/api/cases/{case_id}/refresh")
        assert r.status_code == 409
        # The court is provisional too, and that is the first thing it hits.
        assert "identified on the DCMS portal" in r.text

    async def test_a_complete_court_without_a_cino_still_cannot(
        self, signed_in, db, advocates
    ):
        from app.models import Court

        court = Court(
            name="ACJM Trivandrum",
            portal_state="KERALA",
            portal_district="THIRUVANANTHAPURAM",
            portal_establishment="Addl. Chief Judicial Magistrate Court, Thiruvananthapuram",
        )
        db.add(court)
        await db.commit()

        r = await signed_in.post(
            "/api/cases",
            json={
                "court_id": str(court.id),
                "parties": [{"new_party": {"name": "A Client"}, "role": "client"}],
                "assignments": [{"advocate_id": str(advocates["anil"].id), "role": "lead"}],
            },
        )
        assert r.status_code == 201, r.text

        r = await signed_in.post(f"/api/cases/{r.json()['id']}/refresh")
        assert r.status_code == 409
        assert "no CINO" in r.text


class TestSnapshotEndpoints:
    async def test_diff_apply_and_history(self, signed_in, db, session, advocates):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        snapshot = await _snapshot(db, "dcms_case_detail_burst.txt", case_id=case.id)
        await db.commit()

        r = await signed_in.get(f"/api/cases/{case.id}/snapshots/{snapshot.id}/diff")
        assert r.status_code == 200, r.text
        assert r.json()["has_changes"] is True

        r = await signed_in.post(f"/api/cases/{case.id}/snapshots/{snapshot.id}/apply")
        assert r.status_code == 200, r.text
        assert len(r.json()["act_sections"]) == 1

        r = await signed_in.get(f"/api/cases/{case.id}/snapshots")
        assert r.status_code == 200
        statuses = {row["status"] for row in r.json()}
        assert statuses == {"applied", "superseded"}

    async def test_a_snapshot_belonging_to_another_case_is_not_found(
        self, signed_in, db, session, advocates
    ):
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        loose = await _snapshot(db, "dcms_case_found.txt")
        await db.commit()

        r = await signed_in.get(f"/api/cases/{case.id}/snapshots/{loose.id}/diff")
        assert r.status_code == 404
