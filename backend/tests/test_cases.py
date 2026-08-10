"""Phase 1a behaviour.

The tests that matter most here are the ownership ones: what a caller may and may
not write. See ADR-0002.
"""


async def _minimal_case(client, advocate_id, **overrides):
    payload = {
        "new_court_name": "Munsiff Court, Ernakulam",
        "parties": [{"new_party": {"name": "Rajan K"}, "role": "client"}],
        "assignments": [{"advocate_id": advocate_id, "role": "lead"}],
    }
    payload.update(overrides)
    return await client.post("/api/cases", json=payload)


class TestAuth:
    async def test_case_list_needs_a_session(self, client):
        assert (await client.get("/api/cases")).status_code == 401

    async def test_wrong_password_is_refused(self, client, advocates):
        r = await client.post(
            "/api/auth/login", json={"email": "priya@example.com", "password": "nope"}
        )
        assert r.status_code == 401

    async def test_unknown_email_looks_the_same_as_a_wrong_password(self, client, advocates):
        r = await client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "nope"}
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "Wrong email or password"

    async def test_logout_ends_the_session(self, signed_in):
        assert (await signed_in.get("/api/cases")).status_code == 200
        assert (await signed_in.post("/api/auth/logout")).status_code == 204
        assert (await signed_in.get("/api/cases")).status_code == 401


class TestFilingDay:
    """A plaint filed this morning has no CINO and no registration number, and
    must still be able to hold a case."""

    async def test_case_needs_only_court_client_and_advocate(self, signed_in, advocates):
        r = await _minimal_case(signed_in, str(advocates["anil"].id))
        assert r.status_code == 201, r.text
        case = r.json()
        assert case["cino"] is None
        assert case["registration_number"] is None
        assert case["court_status"] is None
        assert case["firm_status"] == "active"

    async def test_inline_court_starts_provisional(self, signed_in, advocates):
        r = await _minimal_case(signed_in, str(advocates["anil"].id))
        court = r.json()["court"]
        assert court["is_complete"] is False
        assert court["portal_district"] is None

    async def test_many_cases_may_have_no_cino(self, signed_in, advocates):
        for _ in range(3):
            r = await _minimal_case(signed_in, str(advocates["anil"].id))
            assert r.status_code == 201
        assert len((await signed_in.get("/api/cases")).json()) == 3

    async def test_a_case_must_have_a_client(self, signed_in, advocates):
        r = await signed_in.post(
            "/api/cases",
            json={
                "new_court_name": "Munsiff Court, Ernakulam",
                "parties": [{"new_party": {"name": "KSEB"}, "role": "opposite_party"}],
                "assignments": [{"advocate_id": str(advocates["anil"].id), "role": "lead"}],
            },
        )
        assert r.status_code == 422


class TestParties:
    async def test_a_party_is_reused_across_cases(self, signed_in, advocates):
        first = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        found = (await signed_in.get("/api/parties", params={"q": "rajan"})).json()
        assert len(found) == 1
        rajan = found[0]["id"]

        r = await signed_in.post(
            "/api/cases",
            json={
                "court_id": first["court"]["id"],
                "parties": [{"party_id": rajan, "role": "client"}],
                "assignments": [{"advocate_id": str(advocates["priya"].id), "role": "lead"}],
            },
        )
        assert r.status_code == 201

        # The point of a Party entity: this question is answerable at all.
        for_rajan = (await signed_in.get(f"/api/parties/{rajan}/cases")).json()
        assert len(for_rajan) == 2

    async def test_same_party_may_be_client_and_opponent_in_different_cases(
        self, signed_in, advocates
    ):
        first = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        rajan = (await signed_in.get("/api/parties", params={"q": "rajan"})).json()[0]["id"]

        r = await signed_in.post(
            "/api/cases",
            json={
                "court_id": first["court"]["id"],
                "parties": [
                    {"new_party": {"name": "Someone Else"}, "role": "client"},
                    {"party_id": rajan, "role": "opposite_party"},
                ],
                "assignments": [{"advocate_id": str(advocates["priya"].id), "role": "lead"}],
            },
        )
        assert r.status_code == 201
        roles = {p["party"]["name"]: p["role"] for p in r.json()["parties"]}
        assert roles["Rajan K"] == "opposite_party"


class TestIdentity:
    async def test_a_cino_belongs_to_one_case(self, signed_in, advocates):
        cino = "KLER010012342024"
        assert (
            await _minimal_case(signed_in, str(advocates["anil"].id), cino=cino)
        ).status_code == 201
        clash = await _minimal_case(signed_in, str(advocates["anil"].id), cino=cino)
        assert clash.status_code == 409
        assert cino in clash.json()["detail"]


class TestOwnership:
    """ADR-0002: the firm owns Firm Status; the court owns Court Status."""

    async def test_firm_status_is_ours_to_change(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.patch(f"/api/cases/{case['id']}", json={"firm_status": "on_hold"})
        assert r.status_code == 200
        assert r.json()["firm_status"] == "on_hold"

    async def test_court_status_cannot_be_set_by_hand(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.patch(f"/api/cases/{case['id']}", json={"court_status": "disposed"})
        assert r.status_code == 422, "writing the court's account by hand must be refused"

    async def test_cino_cannot_be_set_by_hand_after_creation(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.patch(f"/api/cases/{case['id']}", json={"cino": "KLER01999"})
        assert r.status_code == 422


class TestAssignment:
    async def test_my_cases_includes_work_i_do_not_lead(self, signed_in, advocates):
        """The junior who does the drafting must not lose sight of the case."""
        await signed_in.post(
            "/api/cases",
            json={
                "new_court_name": "Munsiff Court, Ernakulam",
                "parties": [{"new_party": {"name": "Rajan K"}, "role": "client"}],
                "assignments": [
                    {"advocate_id": str(advocates["anil"].id), "role": "lead"},
                    {"advocate_id": str(advocates["priya"].id), "role": "assisting"},
                ],
            },
        )
        # Signed in as Priya, who only assists.
        mine = (await signed_in.get("/api/cases", params={"mine": True})).json()
        assert len(mine) == 1

    async def test_an_advocate_holds_one_role_per_case(self, signed_in, advocates):
        r = await signed_in.post(
            "/api/cases",
            json={
                "new_court_name": "Munsiff Court, Ernakulam",
                "parties": [{"new_party": {"name": "Rajan K"}, "role": "client"}],
                "assignments": [
                    {"advocate_id": str(advocates["anil"].id), "role": "lead"},
                    {"advocate_id": str(advocates["anil"].id), "role": "assisting"},
                ],
            },
        )
        assert r.status_code == 400


class TestRelations:
    async def test_an_appeal_points_at_the_case_it_arose_from(self, signed_in, advocates):
        suit = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        appeal = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()

        r = await signed_in.post(
            f"/api/cases/{appeal['id']}/relations",
            params={"related_case_id": suit["id"], "kind": "appeal_of"},
        )
        assert r.status_code == 201

        relations = (await signed_in.get(f"/api/cases/{appeal['id']}/relations")).json()
        assert relations[0]["kind"] == "appeal_of"
        assert relations[0]["related_case_id"] == suit["id"]

    async def test_a_case_cannot_relate_to_itself(self, signed_in, advocates):
        case = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        r = await signed_in.post(
            f"/api/cases/{case['id']}/relations",
            params={"related_case_id": case["id"], "kind": "connected_to"},
        )
        assert r.status_code == 400


class TestListing:
    async def test_list_filters_on_firm_status_not_court_status(self, signed_in, advocates):
        a = (await _minimal_case(signed_in, str(advocates["anil"].id))).json()
        await _minimal_case(signed_in, str(advocates["anil"].id))
        await signed_in.patch(f"/api/cases/{a['id']}", json={"firm_status": "closed"})

        active = (await signed_in.get("/api/cases", params={"firm_status": "active"})).json()
        assert len(active) == 1

    async def test_search_finds_a_case_by_party_name(self, signed_in, advocates):
        await _minimal_case(signed_in, str(advocates["anil"].id))
        found = (await signed_in.get("/api/cases", params={"q": "rajan"})).json()
        assert len(found) == 1
