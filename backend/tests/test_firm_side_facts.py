"""Phase 1e: the facts the firm records about itself.

None of this is court-sourced, so none of it is reachable by a Refresh - that
boundary is asserted in `test_refresh.py::TestRefreshBoundary`, not here. What
these tests fix is the meaning: a Vakalath names one holder, relinquished is not
on hold, and a Firm Status never changes without leaving a record of who.
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Case, Court, FirmStatus, FirmStatusChange
from app.services.cases import load_case
from app.services.refresh import apply_plan
from tests.test_refresh import _ingest, _refresh


@pytest.fixture
def session():
    """The same stand-in for a live `PortalSession` that `test_refresh` uses -
    only these three fields are read."""
    return SimpleNamespace(
        state="KERALA",
        district="THIRUVANANTHAPURAM",
        court="Addl. Chief Judicial Magistrate Court, Thiruvananthapuram",
    )


async def _minimal_case(client, advocate_id, **overrides):
    payload = {
        "new_court_name": "Munsiff Court, Ernakulam",
        "parties": [{"new_party": {"name": "Rajan K"}, "role": "client"}],
        "assignments": [{"advocate_id": advocate_id, "role": "lead"}],
    }
    payload.update(overrides)
    return await client.post("/api/cases", json=payload)


class TestRelinquished:
    async def test_a_case_can_be_relinquished(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.patch(
            f"/api/cases/{case['id']}", json={"firm_status": "relinquished"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["firm_status"] == "relinquished"

    async def test_relinquished_is_not_on_hold(self, signed_in, advocates):
        """The one confusion CONTEXT.md forbids. A relinquished Case must not
        turn up in a list of cases the firm still holds."""
        held = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        gone = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await signed_in.patch(f"/api/cases/{held['id']}", json={"firm_status": "on_hold"})
        await signed_in.patch(f"/api/cases/{gone['id']}", json={"firm_status": "relinquished"})

        on_hold = (await signed_in.get("/api/cases?firm_status=on_hold")).json()
        assert [c["id"] for c in on_hold] == [held["id"]]

        relinquished = (await signed_in.get("/api/cases?firm_status=relinquished")).json()
        assert [c["id"] for c in relinquished] == [gone["id"]]

    async def test_a_relinquished_case_is_still_readable(self, signed_in, advocates):
        """Giving a case up is not deleting it - an appeal may still land."""
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await signed_in.patch(f"/api/cases/{case['id']}", json={"firm_status": "relinquished"})
        assert (await signed_in.get(f"/api/cases/{case['id']}")).status_code == 200


class TestFirmStatusHistory:
    async def test_creating_a_case_opens_the_history(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        history = (await signed_in.get(f"/api/cases/{case['id']}/firm-status-history")).json()
        assert len(history) == 1
        assert history[0]["from_status"] is None
        assert history[0]["to_status"] == "active"
        # Attributed to whoever is signed in, not to the case's lead advocate.
        assert history[0]["changed_by"]["name"] == "Priya Menon"

    async def test_a_change_records_who_and_why(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await signed_in.patch(
            f"/api/cases/{case['id']}",
            json={"firm_status": "relinquished", "firm_status_reason": "Fee unpaid since March"},
        )
        history = (await signed_in.get(f"/api/cases/{case['id']}/firm-status-history")).json()
        assert len(history) == 2
        # Newest first, so the answer to "why does this say relinquished" is the
        # first thing read.
        assert history[0]["from_status"] == "active"
        assert history[0]["to_status"] == "relinquished"
        assert history[0]["reason"] == "Fee unpaid since March"
        assert history[0]["changed_by"]["name"] == "Priya Menon"

    async def test_a_reason_is_optional(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.patch(f"/api/cases/{case['id']}", json={"firm_status": "closed"})
        assert r.status_code == 200
        history = (await signed_in.get(f"/api/cases/{case['id']}/firm-status-history")).json()
        assert history[0]["reason"] is None

    async def test_setting_the_same_status_records_nothing(self, signed_in, advocates):
        """A form that posts every field must not litter the history with
        changes that did not happen."""
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await signed_in.patch(
            f"/api/cases/{case['id']}", json={"firm_status": "active", "case_type": "OS"}
        )
        history = (await signed_in.get(f"/api/cases/{case['id']}/firm-status-history")).json()
        assert len(history) == 1, "only the opening entry"

    async def test_an_unrelated_edit_records_nothing(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await signed_in.patch(f"/api/cases/{case['id']}", json={"case_type": "OS"})
        history = (await signed_in.get(f"/api/cases/{case['id']}/firm-status-history")).json()
        assert len(history) == 1

    async def test_the_history_is_append_only(self, signed_in, advocates, db):
        """Going back to active leaves the relinquishment on the record rather
        than tidying it away."""
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await signed_in.patch(f"/api/cases/{case['id']}", json={"firm_status": "relinquished"})
        await signed_in.patch(f"/api/cases/{case['id']}", json={"firm_status": "active"})

        history = (await signed_in.get(f"/api/cases/{case['id']}/firm-status-history")).json()
        assert [h["to_status"] for h in history] == ["active", "relinquished", "active"]

        rows = (
            (await db.execute(select(FirmStatusChange).where(FirmStatusChange.case_id == case["id"])))
            .scalars()
            .all()
        )
        assert len(rows) == 3


class TestVakalath:
    async def test_a_new_case_has_none(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        assert case["vakalath_advocate"] is None
        assert case["vakalath_holder_name"] is None

    async def test_it_can_name_one_of_the_firms_advocates(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.put(
            f"/api/cases/{case['id']}/vakalath", json={"advocate_id": str(advocates["anil"].id)}
        )
        assert r.status_code == 200, r.text
        assert r.json()["vakalath_advocate"]["name"] == "Anil Kumar"
        assert r.json()["vakalath_holder_name"] is None

    async def test_it_can_name_somebody_outside_the_firm(self, signed_in, advocates):
        """The firm assists on a case without being on record itself. That name
        is not a system user and never will be."""
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.put(
            f"/api/cases/{case['id']}/vakalath", json={"holder_name": "K P Sasidharan"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["vakalath_holder_name"] == "K P Sasidharan"
        assert r.json()["vakalath_advocate"] is None

    async def test_it_never_names_both(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.put(
            f"/api/cases/{case['id']}/vakalath",
            json={"advocate_id": str(advocates["anil"].id), "holder_name": "K P Sasidharan"},
        )
        assert r.status_code == 422

    async def test_one_holder_replaces_the_other(self, signed_in, advocates):
        """A vakalath returned and a fresh one filed in another name. There is
        at most one, so the outside name must not survive underneath."""
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await signed_in.put(
            f"/api/cases/{case['id']}/vakalath", json={"holder_name": "K P Sasidharan"}
        )
        r = await signed_in.put(
            f"/api/cases/{case['id']}/vakalath", json={"advocate_id": str(advocates["priya"].id)}
        )
        assert r.json()["vakalath_advocate"]["name"] == "Priya Menon"
        assert r.json()["vakalath_holder_name"] is None

    async def test_giving_neither_clears_it(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await signed_in.put(
            f"/api/cases/{case['id']}/vakalath", json={"advocate_id": str(advocates["anil"].id)}
        )
        r = await signed_in.put(f"/api/cases/{case['id']}/vakalath", json={})
        assert r.status_code == 200
        assert r.json()["vakalath_advocate"] is None
        assert r.json()["vakalath_holder_name"] is None

    async def test_an_unknown_advocate_is_refused(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.put(
            f"/api/cases/{case['id']}/vakalath", json={"advocate_id": str(uuid.uuid4())}
        )
        assert r.status_code == 404

    async def test_a_blank_outside_name_is_no_vakalath(self, signed_in, advocates):
        """Whitespace is not a holder. Yes/no is read off whether a name is
        there, so a blank must land as none rather than as a nameless yes."""
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.put(f"/api/cases/{case['id']}/vakalath", json={"holder_name": "   "})
        assert r.status_code == 200
        assert r.json()["vakalath_holder_name"] is None


class TestPartyContact:
    async def test_a_phone_and_a_note_can_be_added_afterwards(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        party_id = case["parties"][0]["party"]["id"]

        r = await signed_in.patch(
            f"/api/parties/{party_id}",
            json={"phone": "9847012345", "notes": "Speaks only Malayalam"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["phone"] == "9847012345"
        assert r.json()["notes"] == "Speaks only Malayalam"

    async def test_contact_details_follow_the_party_across_cases(self, signed_in, advocates):
        """The point of a Party existing independently of any Case: the number
        is the person's, entered once."""
        first = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        party_id = first["parties"][0]["party"]["id"]
        await signed_in.patch(f"/api/parties/{party_id}", json={"phone": "9847012345"})

        second = (
            await _minimal_case(
                signed_in,
                str(advocates["anil"].id),
                parties=[{"party_id": party_id, "role": "client"}],
            )
        ).json()
        assert second["parties"][0]["party"]["phone"] == "9847012345"

    async def test_a_phone_can_be_given_when_the_party_is_created(self, signed_in, advocates):
        r = await _minimal_case(
            signed_in,
            str(advocates["anil"].id),
            parties=[
                {"new_party": {"name": "Rajan K", "phone": "9847012345"}, "role": "client"}
            ],
        )
        assert r.status_code == 201, r.text
        assert r.json()["parties"][0]["party"]["phone"] == "9847012345"

    async def test_a_blank_phone_clears_it(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        party_id = case["parties"][0]["party"]["id"]
        await signed_in.patch(f"/api/parties/{party_id}", json={"phone": "9847012345"})
        r = await signed_in.patch(f"/api/parties/{party_id}", json={"phone": "  "})
        assert r.json()["phone"] is None

    async def test_a_party_cannot_be_left_nameless(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        party_id = case["parties"][0]["party"]["id"]
        r = await signed_in.patch(f"/api/parties/{party_id}", json={"name": "   "})
        assert r.status_code == 422

    async def test_unset_fields_are_left_alone(self, signed_in, advocates):
        """A screen that edits only a phone number posts only a phone number,
        and must not blank the note it never showed."""
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        party_id = case["parties"][0]["party"]["id"]
        await signed_in.patch(f"/api/parties/{party_id}", json={"notes": "Call after 6"})
        r = await signed_in.patch(f"/api/parties/{party_id}", json={"phone": "9847012345"})
        assert r.json()["notes"] == "Call after 6"
        assert r.json()["phone"] == "9847012345"


class TestNoneOfThisIsTheCourts:
    """These four facts are the firm's own. A Refresh replaces every
    court-sourced fact and touches nothing else (rule 1, ADR-0007) - so it must
    reach none of this."""

    async def test_a_refresh_leaves_the_vakalath_and_the_relinquishment_alone(
        self, db, session, advocates
    ):
        """Actually refreshed, not inspected: ingest a case, record the firm's
        own facts on it, then apply a fuller Snapshot over the top."""
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        fresh = await load_case(db, case.id)
        fresh.firm_status = FirmStatus.relinquished
        fresh.vakalath_advocate_id = advocates["priya"].id
        await db.commit()

        _, plan = await _refresh(db, case, advocates)
        applied = await apply_plan(db, plan, advocates["anil"])

        # The court's account moved; the firm's own claims did not.
        assert applied.firm_status is FirmStatus.relinquished
        assert applied.vakalath_advocate_id == advocates["priya"].id
        assert applied.court_status is not None

    async def test_a_refresh_does_not_write_the_status_history(
        self, db, session, advocates
    ):
        """A Refresh cannot change the Firm Status, so it has nothing to record
        - the history must not gain an entry for a court event."""
        case = await _ingest(db, session, advocates, "dcms_case_found.txt")
        before = (
            await db.execute(
                select(FirmStatusChange).where(FirmStatusChange.case_id == case.id)
            )
        ).scalars().all()

        _, plan = await _refresh(db, case, advocates)
        await apply_plan(db, plan, advocates["anil"])

        after = (
            await db.execute(
                select(FirmStatusChange).where(FirmStatusChange.case_id == case.id)
            )
        ).scalars().all()
        assert len(after) == len(before) == 1, "only the entry Ingestion opened"

    async def test_a_snapshot_cannot_carry_a_vakalath(self, db, advocates):
        """Belt and braces on the model itself: the check constraint holds even
        when nothing goes through the API."""
        court = Court(name="Munsiff Court, Ernakulam")
        db.add(court)
        await db.flush()

        case = Case(
            court_id=court.id,
            firm_status=FirmStatus.active,
            vakalath_advocate_id=advocates["anil"].id,
            vakalath_holder_name="K P Sasidharan",
        )
        db.add(case)
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
