"""`record_case_types` is how the portal's own case-type dropdown ends up in the
`case_types` table - called from `choose_court` every time an ingestion session
reads it, opportunistically rather than through any dedicated one-off pull.
"""

from sqlalchemy import select

from app.models import CaseType
from app.services.case_types import record_case_types


async def _codes(db) -> set[str]:
    return {c.code for c in (await db.execute(select(CaseType))).scalars()}


class TestRecordCaseTypes:
    async def test_it_stores_codes_seen_for_the_first_time(self, db):
        await record_case_types(db, ["OP", "Crl.MP"])
        assert await _codes(db) == {"OP", "Crl.MP"}

    async def test_a_code_already_known_is_not_duplicated(self, db):
        db.add(CaseType(code="OP"))
        await db.commit()

        await record_case_types(db, ["OP", "OS"])
        assert await _codes(db) == {"OP", "OS"}

    async def test_blank_entries_from_the_portal_are_ignored(self, db):
        await record_case_types(db, ["OP", "  ", ""])
        assert await _codes(db) == {"OP"}
