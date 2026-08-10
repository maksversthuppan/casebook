"""filing and registration dates are days, not moments

A Case's filing and registration dates were `timestamptz` columns holding what
is conceptually a date. Writing a `date` to one stores IST midnight, and
reading that instant back as UTC gives the previous evening - so every Case
ingested before this read both dates one day early. The same trap the portal's
own `$D` encoding sets (`flight._parse_portal_date`), one layer further in.

Converting in `Asia/Kolkata` rather than UTC is what makes this a fix rather
than a second shift: it recovers the day that was meant, not the day the
instant happens to fall on in UTC.

Revision ID: 7c41ab0d9e52
Revises: 3210902b9f8e
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c41ab0d9e52"
down_revision: Union[str, Sequence[str], None] = "3210902b9f8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in ("filing_date", "registration_date"):
        op.alter_column(
            "cases",
            column,
            type_=sa.Date(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
            postgresql_using=f"({column} AT TIME ZONE 'Asia/Kolkata')::date",
        )


def downgrade() -> None:
    for column in ("filing_date", "registration_date"):
        op.alter_column(
            "cases",
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.Date(),
            existing_nullable=True,
            postgresql_using=f"({column}::timestamp AT TIME ZONE 'Asia/Kolkata')",
        )
