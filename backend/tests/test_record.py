"""Phase 1b: hearings, diary entries, notes and the timeline.

The ownership guards here are the ones that make "Refresh from DCMS" safe to
press later. See ADR-0002.
"""

import datetime as dt

from sqlalchemy import select

from app.models import Case, DiaryEntry, Hearing, HearingSource, HearingState

TODAY = dt.date(2026, 8, 6)
LAST_MONTH = dt.date(2026, 7, 6)
NEXT_MONTH = dt.date(2026, 9, 6)


async def make_case(client, advocate_id):
    r = await client.post(
        "/api/cases",
        json={
            "new_court_name": "Munsiff Court, Ernakulam",
            "parties": [{"new_party": {"name": "Rajan K"}, "role": "client"}],
            "assignments": [{"advocate_id": advocate_id, "role": "lead"}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestFirmRecordedHearings:
    """The firm learns a date in open court, days before the portal shows it.
    That is what makes the case usable with no DCMS integration at all."""

    async def test_an_advocate_can_record_the_next_date(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        r = await signed_in.post(
            f"/api/cases/{case['id']}/hearings",
            json={"date": NEXT_MONTH.isoformat(), "purpose": "for written statement"},
        )
        assert r.status_code == 201, r.text
        h = r.json()
        assert h["source"] == "firm"
        assert h["state"] == "scheduled"
        assert h["recorded_by"]["name"] == "Priya Menon"

    async def test_one_posting_per_date(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        body = {"date": NEXT_MONTH.isoformat()}
        assert (
            await signed_in.post(f"/api/cases/{case['id']}/hearings", json=body)
        ).status_code == 201
        clash = await signed_in.post(f"/api/cases/{case['id']}/hearings", json=body)
        assert clash.status_code == 409

    async def test_source_cannot_be_claimed_as_court(self, signed_in, advocates):
        """Nothing created through the API may pretend the court said it."""
        case = await make_case(signed_in, str(advocates["anil"].id))
        r = await signed_in.post(
            f"/api/cases/{case['id']}/hearings",
            json={"date": NEXT_MONTH.isoformat(), "source": "court"},
        )
        assert r.status_code == 422


class TestCourtOwnedHearings:
    async def test_a_court_hearing_cannot_be_edited_by_hand(self, signed_in, advocates, db):
        case = await make_case(signed_in, str(advocates["anil"].id))
        # Stand in for what a Snapshot will write in phase 1d.
        db.add(
            Hearing(
                case_id=case["id"],
                date=LAST_MONTH,
                state=HearingState.held,
                source=HearingSource.court,
                outcome="adjourned",
            )
        )
        await db.commit()
        hearing = (await db.execute(select(Hearing))).unique().scalar_one()

        r = await signed_in.patch(
            f"/api/cases/{case['id']}/hearings/{hearing.id}", json={"outcome": "dismissed"}
        )
        assert r.status_code == 409

        gone = await signed_in.delete(f"/api/cases/{case['id']}/hearings/{hearing.id}")
        assert gone.status_code == 409


class TestRepresentation:
    """Who is on record as having represented the firm at a Hearing - firm-
    authored, unlike the rest of a court-sourced Hearing (CONTEXT.md)."""

    async def test_settable_on_a_court_sourced_hearing(self, signed_in, advocates, db):
        """The one field a refresh's edit lock does not cover."""
        case = await make_case(signed_in, str(advocates["anil"].id))
        db.add(
            Hearing(
                case_id=case["id"],
                date=LAST_MONTH,
                state=HearingState.held,
                source=HearingSource.court,
                outcome="adjourned",
            )
        )
        await db.commit()
        hearing = (await db.execute(select(Hearing))).unique().scalar_one()

        r = await signed_in.put(
            f"/api/cases/{case['id']}/hearings/{hearing.id}/representation",
            json={"advocate_id": str(advocates["anil"].id)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["represented_by_advocate"]["name"] == "Anil Kumar"
        assert r.json()["represented_by_clerk"] is None

        # The court-owned fields are still locked.
        assert (
            await signed_in.patch(
                f"/api/cases/{case['id']}/hearings/{hearing.id}", json={"outcome": "dismissed"}
            )
        ).status_code == 409

    async def test_a_clerk_can_be_recorded_instead(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        h = (
            await signed_in.post(
                f"/api/cases/{case['id']}/hearings", json={"date": NEXT_MONTH.isoformat()}
            )
        ).json()

        clerk = (await signed_in.post("/api/clerks", json={"name": "Suresh"})).json()
        r = await signed_in.put(
            f"/api/cases/{case['id']}/hearings/{h['id']}/representation",
            json={"clerk_id": clerk["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["represented_by_clerk"]["name"] == "Suresh"

    async def test_rejects_both_at_once(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        h = (
            await signed_in.post(
                f"/api/cases/{case['id']}/hearings", json={"date": NEXT_MONTH.isoformat()}
            )
        ).json()
        clerk = (await signed_in.post("/api/clerks", json={"name": "Suresh"})).json()

        r = await signed_in.put(
            f"/api/cases/{case['id']}/hearings/{h['id']}/representation",
            json={"advocate_id": str(advocates["anil"].id), "clerk_id": clerk["id"]},
        )
        assert r.status_code == 422

    async def test_clearing_it(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        h = (
            await signed_in.post(
                f"/api/cases/{case['id']}/hearings", json={"date": NEXT_MONTH.isoformat()}
            )
        ).json()
        await signed_in.put(
            f"/api/cases/{case['id']}/hearings/{h['id']}/representation",
            json={"advocate_id": str(advocates["anil"].id)},
        )

        r = await signed_in.put(
            f"/api/cases/{case['id']}/hearings/{h['id']}/representation", json={}
        )
        assert r.status_code == 200, r.text
        assert r.json()["represented_by_advocate"] is None


class TestNextHearingDate:
    """Derived from the Hearings, never stored, so it cannot drift."""

    async def test_it_is_the_earliest_scheduled_hearing(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        for d in (NEXT_MONTH, TODAY):
            await signed_in.post(
                f"/api/cases/{case['id']}/hearings", json={"date": d.isoformat()}
            )

        fresh = (await signed_in.get(f"/api/cases/{case['id']}")).json()
        assert fresh["next_hearing_date"] == TODAY.isoformat()

    async def test_a_held_hearing_no_longer_counts(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        first = (
            await signed_in.post(
                f"/api/cases/{case['id']}/hearings", json={"date": TODAY.isoformat()}
            )
        ).json()
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings", json={"date": NEXT_MONTH.isoformat()}
        )

        await signed_in.patch(
            f"/api/cases/{case['id']}/hearings/{first['id']}",
            json={"state": "held", "outcome": "adjourned"},
        )
        fresh = (await signed_in.get(f"/api/cases/{case['id']}")).json()
        assert fresh["next_hearing_date"] == NEXT_MONTH.isoformat()

    async def test_no_hearings_means_no_next_date(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        assert case["next_hearing_date"] is None

    async def test_a_passed_date_is_still_shown(self, signed_in, advocates):
        """Not filtered to the future: a scheduled date that has gone by with no
        outcome is exactly what an advocate needs to see."""
        case = await make_case(signed_in, str(advocates["anil"].id))
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings", json={"date": LAST_MONTH.isoformat()}
        )
        fresh = (await signed_in.get(f"/api/cases/{case['id']}")).json()
        assert fresh["next_hearing_date"] == LAST_MONTH.isoformat()


class TestDiary:
    async def test_an_entry_is_attributed_to_its_author(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        r = await signed_in.post(
            f"/api/cases/{case['id']}/diary",
            json={"date": TODAY.isoformat(), "body": "Third adjournment sought."},
        )
        assert r.status_code == 201
        assert r.json()["author"]["name"] == "Priya Menon"

    async def test_an_entry_needs_no_hearing(self, signed_in, advocates):
        """Client meetings, drafting, a trip to the sub-registrar."""
        case = await make_case(signed_in, str(advocates["anil"].id))
        r = await signed_in.post(
            f"/api/cases/{case['id']}/diary",
            json={"date": TODAY.isoformat(), "body": "Met the client about fees."},
        )
        assert r.status_code == 201
        fresh = (await signed_in.get(f"/api/cases/{case['id']}")).json()
        assert fresh["next_hearing_date"] is None

    async def test_several_entries_on_one_date_are_fine(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        for body in ("Morning: mention.", "Afternoon: spoke to counsel."):
            r = await signed_in.post(
                f"/api/cases/{case['id']}/diary",
                json={"date": TODAY.isoformat(), "body": body},
            )
            assert r.status_code == 201

    async def test_only_the_author_may_change_it(self, signed_in, advocates, db):
        case = await make_case(signed_in, str(advocates["anil"].id))
        db.add(
            DiaryEntry(
                case_id=case["id"],
                date=TODAY,
                body="Anil's own account of the day.",
                author_id=advocates["anil"].id,
            )
        )
        await db.commit()
        entry = (await db.execute(select(DiaryEntry))).unique().scalar_one()

        # Signed in as Priya.
        r = await signed_in.patch(
            f"/api/cases/{case['id']}/diary/{entry.id}", json={"body": "rewritten"}
        )
        assert r.status_code == 403
        assert (
            await signed_in.delete(f"/api/cases/{case['id']}/diary/{entry.id}")
        ).status_code == 403


class TestTimeline:
    async def test_hearings_and_entries_interleave_by_date(self, signed_in, advocates):
        case = await make_case(signed_in, str(advocates["anil"].id))
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings",
            json={"date": LAST_MONTH.isoformat(), "state": "held", "outcome": "adjourned"},
        )
        await signed_in.post(
            f"/api/cases/{case['id']}/diary",
            json={"date": LAST_MONTH.isoformat(), "body": "Third adjournment."},
        )
        await signed_in.post(
            f"/api/cases/{case['id']}/diary",
            json={"date": TODAY.isoformat(), "body": "Met the client."},
        )

        items = (await signed_in.get(f"/api/cases/{case['id']}/timeline")).json()
        assert [(i["date"], i["kind"]) for i in items] == [
            (TODAY.isoformat(), "diary"),
            (LAST_MONTH.isoformat(), "hearing"),
            (LAST_MONTH.isoformat(), "diary"),
        ]

    async def test_notes_stay_off_the_timeline(self, signed_in, advocates):
        """A note is about the case as a whole, not about a day."""
        case = await make_case(signed_in, str(advocates["anil"].id))
        r = await signed_in.post(
            f"/api/cases/{case['id']}/notes", json={"body": "Client is hard to reach."}
        )
        assert r.status_code == 201
        assert (await signed_in.get(f"/api/cases/{case['id']}/timeline")).json() == []
        assert len((await signed_in.get(f"/api/cases/{case['id']}/notes")).json()) == 1


class TestRefreshBoundary:
    """The guarantee that makes the refresh button safe to press.

    Phase 1d will apply Snapshots for real; this fixes the boundary now, so that
    the code written then has something to violate.
    """

    async def test_writing_the_court_record_leaves_authored_text_untouched(
        self, signed_in, advocates, db
    ):
        case = await make_case(signed_in, str(advocates["anil"].id))
        written = (
            await signed_in.post(
                f"/api/cases/{case['id']}/diary",
                json={
                    "date": LAST_MONTH.isoformat(),
                    "body": "Judge indicated no further indulgence. Told Rajan to expect "
                    "trial by November.",
                },
            )
        ).json()

        # What applying a Snapshot is allowed to touch.
        db.add(
            Hearing(
                case_id=case["id"],
                date=LAST_MONTH,
                state=HearingState.held,
                source=HearingSource.court,
                purpose="for written statement",
                outcome="adjourned",
            )
        )
        the_case = await db.get(Case, case["id"])
        the_case.court_status = "disposed"
        await db.commit()

        after = (await signed_in.get(f"/api/cases/{case['id']}/diary")).json()
        assert len(after) == 1
        assert after[0]["body"] == written["body"], "authored text must survive verbatim"
        assert after[0]["author"]["id"] == written["author"]["id"]
        assert after[0]["id"] == written["id"]
