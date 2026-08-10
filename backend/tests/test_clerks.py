"""Clerks: named firm members with no login of their own (CONTEXT.md)."""


class TestClerks:
    async def test_create_and_list(self, signed_in):
        r = await signed_in.post("/api/clerks", json={"name": "Suresh"})
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "Suresh"

        listed = (await signed_in.get("/api/clerks")).json()
        assert [c["name"] for c in listed] == ["Suresh"]

    async def test_get_by_id(self, signed_in):
        created = (await signed_in.post("/api/clerks", json={"name": "Suresh"})).json()
        r = await signed_in.get(f"/api/clerks/{created['id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "Suresh"

    async def test_unknown_clerk_is_404(self, signed_in):
        r = await signed_in.get("/api/clerks/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404
