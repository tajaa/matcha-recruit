"""Add authority_item_classifications.jurisdiction_scope (sub-index reach).

A classification ("the tag") is normally as wide as its authority index. Some
items are narrower than their index — a state code section that binds only named
counties/cities. This nullable JSONB expresses that reach:

    {"level": "county"|"city", "names": ["Los Angeles", ...]}

NULL = whole-index reach = exact current behavior, so no backfill. It stays
jurisdiction-portable: it narrows the item's OWN reach (a fact stated in the
law), never a per-jurisdiction value.

Revision ID: scopetag01
Revises: rkdsev01
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op


revision: str = "scopetag01"
down_revision: Union[str, Sequence[str], None] = "rkdsev01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE authority_item_classifications "
        "ADD COLUMN IF NOT EXISTS jurisdiction_scope JSONB"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE authority_item_classifications DROP COLUMN IF EXISTS jurisdiction_scope"
    )
