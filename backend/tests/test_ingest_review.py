"""Turning a reviewed Snapshot into a Case (ADR-0005).

Exercises `create_case_from_snapshot` directly against the real captured
payload, rather than through the API - the wizard steps ahead of it need a
live Playwright session, which these tests have no business starting.
"""

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.dcms.flight import extract_case, parse_flight, split_responses
from app.models import Court, DcmsSnapshot, Hearing, PartyRole, SnapshotStatus
from app.schemas.ingest import ReviewIn, ReviewPartyIn
from app.services.ingest import create_case_from_snapshot

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# Both fixtures share the same adlData: two more petitioners and one more
# respondent beyond the lead names, real individuals a Person must link or
# create too (ADR-0005) - reused across every test below.
PETITIONER_OTHERS = [
    ReviewPartyIn(new_party={"name": "Diya R Binu"}),
    ReviewPartyIn(new_party={"name": "Nila R Binu"}),
]
RESPONDENT_OTHERS = [ReviewPartyIn(new_party={"name": "Leela R"})]


@pytest.fixture
def session():
    """Stands in for a live `PortalSession` - only these three fields are used."""
    return SimpleNamespace(
        state="KERALA",
        district="THIRUVANANTHAPURAM",
        court="Addl. Chief Judicial Magistrate Court, Thiruvananthapuram",
    )


async def _snapshot(db) -> DcmsSnapshot:
    raw = _load("dcms_case_found.txt")
    snapshot = DcmsSnapshot(
        search_mode="cnr",
        search_value="KLTV080027432025",
        raw_response=raw,
        parsed=parse_flight(raw),
        fetched_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def _snapshot_with_full_detail(db) -> DcmsSnapshot:
    """A Snapshot whose raw_response is the whole burst, not just the first
    response - what a real `submit()` capture produces (see ROADMAP.md,
    2026-08-09)."""
    raw = _load("dcms_case_detail_burst.txt")
    snapshot = DcmsSnapshot(
        search_mode="cnr",
        search_value="KLTV080027432025",
        raw_response=raw,
        parsed=parse_flight(split_responses(raw)[0]),
        fetched_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


class TestCreateCaseFromSnapshot:
    async def test_creates_the_court_complete(self, db, session, advocates):
        snapshot = await _snapshot(db)
        portal_case = extract_case(snapshot.parsed)
        payload = ReviewIn(
            client_side="respondent",
            petitioner=ReviewPartyIn(new_party={"name": "Rekha Devi P S and 2 Others"}),
            respondent=ReviewPartyIn(new_party={"name": "BINU S L and ANOTHER"}),
            petitioner_others=PETITIONER_OTHERS,
            respondent_others=RESPONDENT_OTHERS,
            assignments=[{"advocate_id": advocates["anil"].id, "role": "lead"}],
        )

        case = await create_case_from_snapshot(
            db, session, snapshot, portal_case, payload, advocates["anil"]
        )

        assert case.court.is_complete
        assert case.court.portal_district == "THIRUVANANTHAPURAM"
        assert case.cino == "KLTV080027432025"
        assert case.case_type == "MC"
        assert case.court_status == "Pending"
        assert case.firm_status == "active"

    async def test_reuses_an_existing_complete_court(self, db, session, advocates):
        existing = Court(
            name="ACJM Trivandrum",
            portal_state="KERALA",
            portal_district="THIRUVANANTHAPURAM",
            portal_establishment="Addl. Chief Judicial Magistrate Court, Thiruvananthapuram",
        )
        db.add(existing)
        await db.flush()

        snapshot = await _snapshot(db)
        portal_case = extract_case(snapshot.parsed)
        payload = ReviewIn(
            client_side="petitioner",
            petitioner=ReviewPartyIn(new_party={"name": "Rekha Devi P S and 2 Others"}),
            respondent=ReviewPartyIn(new_party={"name": "BINU S L and ANOTHER"}),
            petitioner_others=PETITIONER_OTHERS,
            respondent_others=RESPONDENT_OTHERS,
            assignments=[{"advocate_id": advocates["anil"].id, "role": "lead"}],
        )

        case = await create_case_from_snapshot(
            db, session, snapshot, portal_case, payload, advocates["anil"]
        )
        assert case.court_id == existing.id

    async def test_client_side_decides_the_party_role(self, db, session, advocates):
        snapshot = await _snapshot(db)
        portal_case = extract_case(snapshot.parsed)
        payload = ReviewIn(
            client_side="respondent",
            petitioner=ReviewPartyIn(new_party={"name": "Rekha Devi P S and 2 Others"}),
            respondent=ReviewPartyIn(new_party={"name": "BINU S L and ANOTHER"}),
            petitioner_others=PETITIONER_OTHERS,
            respondent_others=RESPONDENT_OTHERS,
            assignments=[{"advocate_id": advocates["anil"].id, "role": "lead"}],
        )

        case = await create_case_from_snapshot(
            db, session, snapshot, portal_case, payload, advocates["anil"]
        )

        by_name = {cp.party.name: cp for cp in case.parties}
        assert by_name["BINU S L and ANOTHER"].role == PartyRole.client
        assert by_name["Rekha Devi P S and 2 Others"].role == PartyRole.opposite_party
        # The portal's own words are kept beside the link, not just the Party.
        assert by_name["BINU S L and ANOTHER"].portal_raw_name == "BINU S L and ANOTHER"

    async def test_creates_scheduled_and_held_hearings_but_not_first_hearing(
        self, db, session, advocates
    ):
        snapshot = await _snapshot(db)
        portal_case = extract_case(snapshot.parsed)
        payload = ReviewIn(
            client_side="petitioner",
            petitioner=ReviewPartyIn(new_party={"name": "Rekha Devi P S and 2 Others"}),
            respondent=ReviewPartyIn(new_party={"name": "BINU S L and ANOTHER"}),
            petitioner_others=PETITIONER_OTHERS,
            respondent_others=RESPONDENT_OTHERS,
            assignments=[{"advocate_id": advocates["anil"].id, "role": "lead"}],
        )

        case = await create_case_from_snapshot(
            db, session, snapshot, portal_case, payload, advocates["anil"]
        )

        rows = (
            (await db.execute(select(Hearing).where(Hearing.case_id == case.id)))
            .scalars()
            .all()
        )
        by_date = {h.date: h.state for h in rows}
        assert by_date[portal_case.next_hearing] == "scheduled"
        assert by_date[portal_case.last_hearing] == "held"
        assert portal_case.first_hearing not in by_date

    async def test_applies_the_snapshot(self, db, session, advocates):
        snapshot = await _snapshot(db)
        portal_case = extract_case(snapshot.parsed)
        payload = ReviewIn(
            client_side="petitioner",
            petitioner=ReviewPartyIn(new_party={"name": "Rekha Devi P S and 2 Others"}),
            respondent=ReviewPartyIn(new_party={"name": "BINU S L and ANOTHER"}),
            petitioner_others=PETITIONER_OTHERS,
            respondent_others=RESPONDENT_OTHERS,
            assignments=[{"advocate_id": advocates["anil"].id, "role": "lead"}],
        )

        case = await create_case_from_snapshot(
            db, session, snapshot, portal_case, payload, advocates["anil"]
        )

        assert snapshot.status == SnapshotStatus.applied
        assert snapshot.case_id == case.id
        assert snapshot.decided_by_id == advocates["anil"].id

    async def test_refuses_an_already_decided_snapshot(self, db, session, advocates):
        snapshot = await _snapshot(db)
        portal_case = extract_case(snapshot.parsed)
        payload = ReviewIn(
            client_side="petitioner",
            petitioner=ReviewPartyIn(new_party={"name": "Rekha Devi P S and 2 Others"}),
            respondent=ReviewPartyIn(new_party={"name": "BINU S L and ANOTHER"}),
            petitioner_others=PETITIONER_OTHERS,
            respondent_others=RESPONDENT_OTHERS,
            assignments=[{"advocate_id": advocates["anil"].id, "role": "lead"}],
        )
        await create_case_from_snapshot(db, session, snapshot, portal_case, payload, advocates["anil"])

        with pytest.raises(HTTPException) as exc:
            await create_case_from_snapshot(
                db, session, snapshot, portal_case, payload, advocates["anil"]
            )
        assert exc.value.status_code == 409


class TestCreateCaseFromSnapshotWithFullDetail:
    """The rest of the burst - case history, acts & section, crime details,
    the other side's counsel - actually lands on the Case (ROADMAP.md,
    2026-08-09)."""

    async def _case(self, db, session, advocates):
        snapshot = await _snapshot_with_full_detail(db)
        portal_case = extract_case(snapshot.parsed)
        payload = ReviewIn(
            client_side="petitioner",
            petitioner=ReviewPartyIn(new_party={"name": "Rekha Devi P S and 2 Others"}),
            respondent=ReviewPartyIn(new_party={"name": "BINU S L and ANOTHER"}),
            petitioner_others=PETITIONER_OTHERS,
            respondent_others=RESPONDENT_OTHERS,
            assignments=[{"advocate_id": advocates["anil"].id, "role": "lead"}],
        )
        return await create_case_from_snapshot(
            db, session, snapshot, portal_case, payload, advocates["anil"]
        )

    async def test_creates_the_full_hearing_history_with_presiding_officer(
        self, db, session, advocates
    ):
        case = await self._case(db, session, advocates)
        rows = (
            (await db.execute(select(Hearing).where(Hearing.case_id == case.id)))
            .scalars()
            .all()
        )
        # Ten held hearings from the history, plus one scheduled - the still
        # -upcoming date the latest history row adjourned to (2026-10-01),
        # which the history itself has no row for yet.
        assert len(rows) == 11
        by_date = {h.date: h for h in rows}

        first = by_date[dt.date(2025, 5, 29)]
        assert first.state == "held"
        assert first.presiding_officer == "Smt.Elsa Catherine George"
        assert "Taken on file as MC 58/2025" in first.outcome
        # The portal reported an order for this date - the order-available
        # signal from the burst's order-metadata response.
        assert first.order_available is True

        scheduled = by_date[dt.date(2026, 10, 1)]
        assert scheduled.state == "scheduled"

    async def test_creates_crime_details_even_though_mostly_empty(self, db, session, advocates):
        case = await self._case(db, session, advocates)
        assert case.crime_details is not None
        assert case.crime_details.police_station == "Thiruvananthapuram City Medical College PS"
        assert case.crime_details.fir_no is None

    async def test_creates_act_sections(self, db, session, advocates):
        case = await self._case(db, session, advocates)
        assert len(case.act_sections) == 1
        assert case.act_sections[0].section == "12"

    async def test_creates_counsel_on_the_respondent_case_party(self, db, session, advocates):
        case = await self._case(db, session, advocates)
        by_name = {cp.party.name: cp for cp in case.parties}
        respondent = by_name["BINU S L and ANOTHER"]
        assert {c.name for c in respondent.counsels} == {"AJITH R", "ASHEER A K"}

        petitioner = by_name["Rekha Devi P S and 2 Others"]
        assert petitioner.counsels == []

    async def test_creates_the_individuals_the_lead_names_stand_in_for(
        self, db, session, advocates
    ):
        """"and 2 Others"/"and ANOTHER" are not just words on the lead row -
        each is a real Party of their own now, linked by a person, same as
        the lead party (ADR-0005)."""
        case = await self._case(db, session, advocates)
        by_name = {cp.party.name: cp for cp in case.parties}

        assert set(by_name) == {
            "Rekha Devi P S and 2 Others",
            "Diya R Binu",
            "Nila R Binu",
            "BINU S L and ANOTHER",
            "Leela R",
        }

        # Cause-title order: the lead party is always position 1, the
        # enumerated others follow in the portal's own party_no order.
        assert by_name["Rekha Devi P S and 2 Others"].position == 1
        assert by_name["Diya R Binu"].position == 2
        assert by_name["Nila R Binu"].position == 3
        assert by_name["BINU S L and ANOTHER"].position == 1
        assert by_name["Leela R"].position == 2

        # Role follows the side, not just the lead name (client_side="petitioner").
        assert by_name["Diya R Binu"].role == PartyRole.client
        assert by_name["Leela R"].role == PartyRole.opposite_party

        # Counsel is per individual, not just the lead - this case's "Leela R"
        # happens to share both advocates with the lead respondent, but that
        # is this case's data, not an assumption the parser makes.
        assert {c.name for c in by_name["Leela R"].counsels} == {"AJITH R", "ASHEER A K"}
