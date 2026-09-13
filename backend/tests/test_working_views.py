"""Phase 1c: Tasks, the single search box, and the home dashboard.

The two that carry real weight here are the deadline that follows the court's
calendar - move the hearing and every task due before it moves too, with nothing
edited - and a Task outliving the Diary Entry it arose from.
"""

import datetime as dt

from app.config import today_in_court
from app.models import Counsel

#: The same clock the dashboard uses. Taken from `today_in_court` rather than
#: `date.today()` so the two cannot disagree about which day it is.
TODAY = today_in_court()


async def _case(client, advocate_id, **overrides):
    payload = {
        "new_court_name": "Munsiff Court, Ernakulam",
        "parties": [{"new_party": {"name": "Rajan K"}, "role": "client"}],
        "assignments": [{"advocate_id": advocate_id, "role": "lead"}],
    }
    payload.update(overrides)
    r = await client.post("/api/cases", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def _task(client, case_id, advocate_id, **overrides):
    payload = {"title": "File the counter", "assignee_id": advocate_id}
    payload.update(overrides)
    return await client.post(f"/api/cases/{case_id}/tasks", json=payload)


class TestTasks:
    async def test_a_task_needs_a_title_and_somebody_who_owes_it(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        r = await _task(signed_in, case["id"], str(advocates["anil"].id))
        assert r.status_code == 201, r.text
        assert r.json()["assignee"]["name"] == "Anil Kumar"
        assert r.json()["done_at"] is None

    async def test_a_task_may_have_no_deadline(self, signed_in, advocates):
        """Work owed with no date is still owed."""
        case = await _case(signed_in, str(advocates["anil"].id))
        r = await _task(signed_in, case["id"], str(advocates["anil"].id))
        assert r.json()["due_on"] is None

    async def test_a_fixed_deadline_resolves_to_itself(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        when = (TODAY + dt.timedelta(days=10)).isoformat()
        r = await _task(signed_in, case["id"], str(advocates["anil"].id), due_date=when)
        assert r.json()["due_on"] == when

    async def test_a_deadline_is_never_both_kinds(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        r = await _task(
            signed_in,
            case["id"],
            str(advocates["anil"].id),
            due_date=TODAY.isoformat(),
            due_before_next_hearing=True,
        )
        assert r.status_code == 422

    async def test_setting_one_kind_of_deadline_clears_the_other(self, signed_in, advocates):
        """Two separate edits must not be able to reach the state one edit is
        refused for."""
        case = await _case(signed_in, str(advocates["anil"].id))
        task = (
            await _task(
                signed_in,
                case["id"],
                str(advocates["anil"].id),
                due_date=TODAY.isoformat(),
            )
        ).json()

        r = await signed_in.patch(
            f"/api/cases/{case['id']}/tasks/{task['id']}",
            json={"due_before_next_hearing": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["due_date"] is None
        assert r.json()["due_before_next_hearing"] is True

    async def test_ticking_it_off_records_who_and_when(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        task = (await _task(signed_in, case["id"], str(advocates["anil"].id))).json()
        r = await signed_in.patch(
            f"/api/cases/{case['id']}/tasks/{task['id']}", json={"done": True}
        )
        assert r.json()["done_at"] is not None
        # Anyone in the firm may tick anyone's task off; who did it is kept.
        assert r.json()["done_by"]["name"] == "Priya Menon"

    async def test_it_can_be_un_ticked(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        task = (await _task(signed_in, case["id"], str(advocates["anil"].id))).json()
        await signed_in.patch(f"/api/cases/{case['id']}/tasks/{task['id']}", json={"done": True})
        r = await signed_in.patch(
            f"/api/cases/{case['id']}/tasks/{task['id']}", json={"done": False}
        )
        assert r.json()["done_at"] is None
        assert r.json()["done_by"] is None

    async def test_done_tasks_leave_the_list_but_can_be_asked_for(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        task = (await _task(signed_in, case["id"], str(advocates["anil"].id))).json()
        await signed_in.patch(f"/api/cases/{case['id']}/tasks/{task['id']}", json={"done": True})

        assert (await signed_in.get(f"/api/cases/{case['id']}/tasks")).json() == []
        both = (await signed_in.get(f"/api/cases/{case['id']}/tasks?include_done=true")).json()
        assert len(both) == 1


class TestDueBeforeTheNextHearing:
    """The deadline most litigation actually has. It follows the court's
    calendar, so when the court moves a date the deadline moves with it and
    nobody has to remember to edit anything."""

    async def test_it_resolves_to_the_next_scheduled_hearing(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        hearing_day = TODAY + dt.timedelta(days=14)
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings", json={"date": hearing_day.isoformat()}
        )
        r = await _task(
            signed_in, case["id"], str(advocates["anil"].id), due_before_next_hearing=True
        )
        assert r.json()["due_on"] == hearing_day.isoformat()

    async def test_moving_the_hearing_moves_the_deadline(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        first = TODAY + dt.timedelta(days=14)
        hearing = (
            await signed_in.post(
                f"/api/cases/{case['id']}/hearings", json={"date": first.isoformat()}
            )
        ).json()
        task = (
            await _task(
                signed_in, case["id"], str(advocates["anil"].id), due_before_next_hearing=True
            )
        ).json()
        assert task["due_on"] == first.isoformat()

        moved = TODAY + dt.timedelta(days=21)
        await signed_in.patch(
            f"/api/cases/{case['id']}/hearings/{hearing['id']}", json={"date": moved.isoformat()}
        )

        # The task itself was never touched.
        after = (await signed_in.get(f"/api/cases/{case['id']}/tasks")).json()[0]
        assert after["due_on"] == moved.isoformat()
        assert after["due_date"] is None

    async def test_an_earlier_new_hearing_takes_over_the_deadline(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        later = TODAY + dt.timedelta(days=30)
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings", json={"date": later.isoformat()}
        )
        await _task(
            signed_in, case["id"], str(advocates["anil"].id), due_before_next_hearing=True
        )

        sooner = TODAY + dt.timedelta(days=5)
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings", json={"date": sooner.isoformat()}
        )
        after = (await signed_in.get(f"/api/cases/{case['id']}/tasks")).json()[0]
        assert after["due_on"] == sooner.isoformat()

    async def test_with_no_hearing_scheduled_it_resolves_to_nothing(self, signed_in, advocates):
        """Not an error, and not "due today" - there is simply no date to be
        due before yet."""
        case = await _case(signed_in, str(advocates["anil"].id))
        r = await _task(
            signed_in, case["id"], str(advocates["anil"].id), due_before_next_hearing=True
        )
        assert r.json()["due_on"] is None


class TestATaskOutlivesItsDiaryEntry:
    async def test_deleting_the_entry_keeps_the_task(self, signed_in, advocates):
        """A Task belongs to the Case, not to the entry it arose from
        (CONTEXT.md, "Task")."""
        case = await _case(signed_in, str(advocates["anil"].id))
        entry = (
            await signed_in.post(
                f"/api/cases/{case['id']}/diary",
                json={"date": TODAY.isoformat(), "body": "Client wants the counter filed."},
            )
        ).json()
        task = (
            await _task(
                signed_in, case["id"], str(advocates["anil"].id), diary_entry_id=entry["id"]
            )
        ).json()
        assert task["diary_entry_id"] == entry["id"]

        r = await signed_in.delete(f"/api/cases/{case['id']}/diary/{entry['id']}")
        assert r.status_code == 204

        remaining = (await signed_in.get(f"/api/cases/{case['id']}/tasks")).json()
        assert len(remaining) == 1
        assert remaining[0]["diary_entry_id"] is None, "the link goes, the obligation stays"

    async def test_an_entry_from_another_case_is_refused(self, signed_in, advocates):
        one = await _case(signed_in, str(advocates["anil"].id))
        two = await _case(signed_in, str(advocates["anil"].id))
        entry = (
            await signed_in.post(
                f"/api/cases/{two['id']}/diary",
                json={"date": TODAY.isoformat(), "body": "Different case."},
            )
        ).json()
        r = await _task(
            signed_in, one["id"], str(advocates["anil"].id), diary_entry_id=entry["id"]
        )
        assert r.status_code == 404


class TestSearch:
    async def test_it_finds_a_case_by_part_of_a_number(self, signed_in, advocates):
        await _case(signed_in, str(advocates["anil"].id), registration_number="OS/412/2024")
        hits = (await signed_in.get("/api/search?q=412")).json()
        assert len(hits) == 1
        assert hits[0]["matches"][0]["kind"] == "identifier"

    async def test_it_finds_a_case_by_a_party_name(self, signed_in, advocates):
        await _case(signed_in, str(advocates["anil"].id))
        hits = (await signed_in.get("/api/search?q=Rajan")).json()
        assert len(hits) == 1
        assert hits[0]["matches"][0]["kind"] == "party"
        assert hits[0]["matches"][0]["snippet"] == "Rajan K"

    async def test_it_finds_a_case_by_words_in_the_diary(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        await signed_in.post(
            f"/api/cases/{case['id']}/diary",
            json={"date": TODAY.isoformat(), "body": "Matter adjourned for want of time."},
        )
        # Stemming: the word written was "adjourned".
        hits = (await signed_in.get("/api/search?q=adjourn")).json()
        assert len(hits) == 1
        assert hits[0]["matches"][0]["kind"] == "diary"
        assert "<<" in hits[0]["matches"][0]["snippet"], "the hit is marked in the snippet"

    async def test_it_finds_a_case_by_words_in_a_note(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        await signed_in.post(
            f"/api/cases/{case['id']}/notes", json={"body": "Settlement talks are ongoing."}
        )
        hits = (await signed_in.get("/api/search?q=settlement")).json()
        assert len(hits) == 1
        assert hits[0]["matches"][0]["kind"] == "note"

    async def test_a_case_matching_several_ways_keeps_every_reason(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id), registration_number="OS/1/2024")
        await signed_in.post(
            f"/api/cases/{case['id']}/notes", json={"body": "Rajan is hard to reach."}
        )
        hits = (await signed_in.get("/api/search?q=Rajan")).json()
        assert {m["kind"] for m in hits[0]["matches"]} == {"party", "note"}

    async def test_identifier_hits_rank_above_prose(self, signed_in, advocates):
        prose = await _case(signed_in, str(advocates["anil"].id))
        await signed_in.post(
            f"/api/cases/{prose['id']}/notes", json={"body": "See also OS/412/2024 nearby."}
        )
        numbered = await _case(
            signed_in, str(advocates["anil"].id), registration_number="OS/412/2024"
        )
        hits = (await signed_in.get("/api/search?q=OS/412/2024")).json()
        assert hits[0]["case"]["id"] == numbered["id"]

    async def test_the_status_filter_still_applies(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        await signed_in.patch(f"/api/cases/{case['id']}", json={"firm_status": "relinquished"})
        assert (await signed_in.get("/api/search?q=Rajan")).json() != []
        assert (await signed_in.get("/api/search?q=Rajan&firm_status=active")).json() == []

    async def test_an_empty_query_finds_nothing_rather_than_everything(
        self, signed_in, advocates
    ):
        await _case(signed_in, str(advocates["anil"].id))
        assert (await signed_in.get("/api/search?q=%20%20")).json() == []

    async def test_the_case_type_filter_still_applies(self, signed_in, advocates):
        op = await _case(signed_in, str(advocates["anil"].id), case_type="OP")
        await _case(signed_in, str(advocates["anil"].id), case_type="OS")

        both = (await signed_in.get("/api/search?q=Rajan")).json()
        assert len(both) == 2

        only_op = (await signed_in.get("/api/search?q=Rajan&case_type=OP")).json()
        assert [h["case"]["id"] for h in only_op] == [op["id"]]

    async def test_the_court_filter_still_applies(self, signed_in, advocates):
        first = await _case(signed_in, str(advocates["anil"].id))
        second = await _case(
            signed_in, str(advocates["anil"].id), new_court_name="Family Court, Kochi"
        )

        both = (await signed_in.get("/api/search?q=Rajan")).json()
        assert len(both) == 2

        only_second = (
            await signed_in.get(f"/api/search?q=Rajan&court_id={second['court']['id']}")
        ).json()
        assert [h["case"]["id"] for h in only_second] == [second["id"]]

    async def test_it_finds_a_case_by_our_own_advocates_name(self, signed_in, advocates):
        """Anil Kumar is the assigned advocate - "our lawyer" as the firm
        itself would mean it, not a portal-reported name."""
        await _case(signed_in, str(advocates["anil"].id))
        hits = (await signed_in.get("/api/search?q=Kumar")).json()
        assert len(hits) == 1
        assert hits[0]["matches"][0]["kind"] == "advocate"

    async def test_it_finds_a_case_by_the_vakalath_holders_name(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["anil"].id))
        await signed_in.put(
            f"/api/cases/{case['id']}/vakalath", json={"holder_name": "Ravi Varma"}
        )
        hits = (await signed_in.get("/api/search?q=Varma")).json()
        assert len(hits) == 1
        assert hits[0]["matches"][0]["kind"] == "advocate"

    async def test_it_finds_a_case_by_the_opposite_partys_counsel(
        self, signed_in, advocates, db
    ):
        case = await _case(
            signed_in,
            str(advocates["anil"].id),
            parties=[
                {"new_party": {"name": "Rajan K"}, "role": "client"},
                {"new_party": {"name": "KSEB"}, "role": "opposite_party"},
            ],
        )
        opposite = next(p for p in case["parties"] if p["role"] == "opposite_party")
        db.add(Counsel(case_party_id=opposite["id"], name="Suresh Menon"))
        await db.commit()

        hits = (await signed_in.get("/api/search?q=Menon")).json()
        assert len(hits) == 1
        assert hits[0]["matches"][0]["kind"] == "counsel"

    async def test_counsel_on_our_own_clients_side_is_not_searched(
        self, signed_in, advocates, db
    ):
        """The documented mixup (ROADMAP 2026-08-10, ADR-0008): a Counsel row
        against our own client's CaseParty is ours to avoid surfacing as
        opposing counsel, not a lawyer-name hit."""
        case = await _case(signed_in, str(advocates["anil"].id))
        client_party = case["parties"][0]
        db.add(Counsel(case_party_id=client_party["id"], name="Suresh Menon"))
        await db.commit()

        assert (await signed_in.get("/api/search?q=Menon")).json() == []


class TestDashboard:
    async def test_it_shows_my_hearings_this_week(self, signed_in, advocates):
        """Mine means a case I hold an Assignment on. `signed_in` is Priya."""
        mine = await _case(signed_in, str(advocates["priya"].id))
        theirs = await _case(signed_in, str(advocates["anil"].id))
        soon = (TODAY + dt.timedelta(days=3)).isoformat()
        for c in (mine, theirs):
            await signed_in.post(f"/api/cases/{c['id']}/hearings", json={"date": soon})

        board = (await signed_in.get("/api/dashboard")).json()
        assert [h["case"]["id"] for h in board["hearings"]] == [mine["id"]]

    async def test_a_hearing_beyond_the_week_is_not_shown(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["priya"].id))
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings",
            json={"date": (TODAY + dt.timedelta(days=30)).isoformat()},
        )
        board = (await signed_in.get("/api/dashboard")).json()
        assert board["hearings"] == []

    async def test_a_passed_date_with_nothing_recorded_is_kept_apart(
        self, signed_in, advocates
    ):
        """Not work coming, but a record with a hole in it."""
        case = await _case(signed_in, str(advocates["priya"].id))
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings",
            json={"date": (TODAY - dt.timedelta(days=4)).isoformat()},
        )
        board = (await signed_in.get("/api/dashboard")).json()
        assert board["hearings"] == []
        assert len(board["hearings_passed"]) == 1

    async def test_it_shows_tasks_i_owe_soonest_first(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["priya"].id))
        await _task(
            signed_in,
            case["id"],
            str(advocates["priya"].id),
            title="Later",
            due_date=(TODAY + dt.timedelta(days=9)).isoformat(),
        )
        await _task(
            signed_in,
            case["id"],
            str(advocates["priya"].id),
            title="Sooner",
            due_date=(TODAY + dt.timedelta(days=2)).isoformat(),
        )
        await _task(signed_in, case["id"], str(advocates["priya"].id), title="Undated")
        await _task(signed_in, case["id"], str(advocates["anil"].id), title="Not mine")

        board = (await signed_in.get("/api/dashboard")).json()
        assert [t["title"] for t in board["tasks"]] == ["Sooner", "Later", "Undated"]

    async def test_a_task_due_before_a_hearing_sorts_by_the_hearing(
        self, signed_in, advocates
    ):
        """The whole point of resolving the deadline in SQL: a moving target
        still sorts alongside a fixed date."""
        case = await _case(signed_in, str(advocates["priya"].id))
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings",
            json={"date": (TODAY + dt.timedelta(days=2)).isoformat()},
        )
        await _task(
            signed_in,
            case["id"],
            str(advocates["priya"].id),
            title="Fixed, later",
            due_date=(TODAY + dt.timedelta(days=9)).isoformat(),
        )
        await _task(
            signed_in,
            case["id"],
            str(advocates["priya"].id),
            title="Before the hearing",
            due_before_next_hearing=True,
        )
        board = (await signed_in.get("/api/dashboard")).json()
        assert [t["title"] for t in board["tasks"]] == ["Before the hearing", "Fixed, later"]

    async def test_a_done_task_leaves_the_dashboard(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["priya"].id))
        task = (await _task(signed_in, case["id"], str(advocates["priya"].id))).json()
        await signed_in.patch(f"/api/cases/{case['id']}/tasks/{task['id']}", json={"done": True})
        assert (await signed_in.get("/api/dashboard")).json()["tasks"] == []

    async def test_relinquished_work_is_absent_throughout(self, signed_in, advocates):
        """A view of work in hand. A case the firm has given up is not that."""
        case = await _case(signed_in, str(advocates["priya"].id))
        await signed_in.post(
            f"/api/cases/{case['id']}/hearings",
            json={"date": (TODAY + dt.timedelta(days=3)).isoformat()},
        )
        await _task(signed_in, case["id"], str(advocates["priya"].id))
        await signed_in.patch(f"/api/cases/{case['id']}", json={"firm_status": "relinquished"})

        board = (await signed_in.get("/api/dashboard")).json()
        assert board["hearings"] == []
        assert board["tasks"] == []
        assert board["stale_cases"] == []

    async def test_a_case_never_confirmed_with_dcms_is_stale(self, signed_in, advocates):
        case = await _case(signed_in, str(advocates["priya"].id))
        board = (await signed_in.get("/api/dashboard")).json()
        assert [c["id"] for c in board["stale_cases"]] == [case["id"]]
        assert board["stale_after_days"] == 30
