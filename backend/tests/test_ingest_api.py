"""The `/ingest/{sid}/review` endpoint's own guard clauses.

`create_case_from_snapshot` is exercised directly in `test_ingest_review.py`.
This file drives the HTTP layer instead, registering a session by hand rather
than opening a real Playwright browser - `review()` never touches `session.page`,
so a session with `context=None, page=None` behaves identically for this route.
"""

import secrets
from datetime import datetime, timezone
from pathlib import Path

from app.dcms.flight import parse_flight
from app.dcms.session import PortalSession, registry
from app.models import DcmsSnapshot

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_session(advocate_id, snapshot_id) -> PortalSession:
    now = datetime.now(timezone.utc)
    session = PortalSession(
        id=secrets.token_urlsafe(9),
        advocate_id=advocate_id,
        context=None,
        page=None,
        created_at=now,
        last_used_at=now,
        state="KERALA",
        district="THIRUVANANTHAPURAM",
        court="Addl. Chief Judicial Magistrate Court, Thiruvananthapuram",
        snapshot_id=snapshot_id,
    )
    registry._sessions[session.id] = session
    return session


async def _snapshot(db) -> DcmsSnapshot:
    raw = (FIXTURES / "dcms_case_found.txt").read_text()
    snapshot = DcmsSnapshot(
        search_mode="cnr",
        search_value="KLTV080027432025",
        raw_response=raw,
        parsed=parse_flight(raw),
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    await db.commit()
    return snapshot


def _others_specs(*names: str) -> list[dict]:
    return [{"new_party": {"name": n}} for n in names]


class TestReviewEndpoint:
    async def test_creates_and_applies(self, signed_in, db, advocates):
        snapshot = await _snapshot(db)
        session = _fake_session(advocates["priya"].id, snapshot.id)

        r = await signed_in.post(
            f"/api/ingest/{session.id}/review",
            json={
                "client_side": "respondent",
                "petitioner": {"new_party": {"name": "Rekha Devi P S and 2 Others"}},
                "respondent": {"new_party": {"name": "BINU S L and ANOTHER"}},
                # This case's real payload enumerates two more petitioners and
                # one more respondent beyond the lead names above.
                "petitioner_others": _others_specs("Diya R Binu", "Nila R Binu"),
                "respondent_others": _others_specs("Leela R"),
                "assignments": [{"advocate_id": str(advocates["priya"].id), "role": "lead"}],
            },
        )
        assert r.status_code == 201, r.text
        case = r.json()
        assert case["cino"] == "KLTV080027432025"
        assert case["court"]["is_complete"] is True
        # The session is retired once the Case is created - no browser left running.
        assert registry._sessions.get(session.id) is None

    async def test_refuses_when_a_present_side_has_no_party_spec(self, signed_in, db, advocates):
        snapshot = await _snapshot(db)
        session = _fake_session(advocates["priya"].id, snapshot.id)

        r = await signed_in.post(
            f"/api/ingest/{session.id}/review",
            json={
                "client_side": "petitioner",
                "petitioner": {"new_party": {"name": "Rekha Devi P S and 2 Others"}},
                "petitioner_others": _others_specs("Diya R Binu", "Nila R Binu"),
                # respondent omitted, but the Snapshot has one.
                "assignments": [{"advocate_id": str(advocates["priya"].id), "role": "lead"}],
            },
        )
        assert r.status_code == 400
        assert "respondent" in r.text

    async def test_refuses_when_an_enumerated_individual_has_no_party_spec(
        self, signed_in, db, advocates
    ):
        """Every "and N Others" name is linked or created by a person too, same
        as the lead party - never silently matched (ADR-0005)."""
        snapshot = await _snapshot(db)
        session = _fake_session(advocates["priya"].id, snapshot.id)

        r = await signed_in.post(
            f"/api/ingest/{session.id}/review",
            json={
                "client_side": "respondent",
                "petitioner": {"new_party": {"name": "Rekha Devi P S and 2 Others"}},
                "respondent": {"new_party": {"name": "BINU S L and ANOTHER"}},
                "petitioner_others": _others_specs("Diya R Binu"),  # one short
                "respondent_others": _others_specs("Leela R"),
                "assignments": [{"advocate_id": str(advocates["priya"].id), "role": "lead"}],
            },
        )
        assert r.status_code == 400
        assert "petitioner" in r.text
