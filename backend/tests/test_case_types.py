"""The case-type filter on the search screen draws on this: the fixed
vocabulary DCMS itself offers (OP, Crl.MP, and the like), learned once from an
ingestion session's own case-type dropdown and kept from then on rather than
re-fetched on every search.
"""

from app.models import CaseType


class TestCaseTypesEndpoint:
    async def test_it_lists_stored_case_types_alphabetically(self, signed_in, db):
        db.add_all([CaseType(code="OP"), CaseType(code="Crl.MP")])
        await db.commit()

        r = await signed_in.get("/api/case-types")
        assert r.status_code == 200
        assert [c["code"] for c in r.json()] == ["Crl.MP", "OP"]

    async def test_an_empty_table_is_an_empty_list_not_an_error(self, signed_in):
        r = await signed_in.get("/api/case-types")
        assert r.status_code == 200
        assert r.json() == []

    async def test_it_needs_a_session(self, client):
        assert (await client.get("/api/case-types")).status_code == 401
