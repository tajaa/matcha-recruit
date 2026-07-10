"""store full statute/regulation text on authority_index_items

The registry held citation + heading + source_url only — the actual law was a
link-out. Compliance means reading the obligation itself, so this adds the body
text (fetched from official sources: eCFR full-text XML, CA leginfo/dir.ca.gov,
etc.), the source it came from, when, and a hash for cheap change-detection on
refetch.

Revision ID: statbody01
Revises: codify02
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op


revision: str = "statbody01"
down_revision: Union[str, Sequence[str], None] = "codify02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        ALTER TABLE authority_index_items
            ADD COLUMN IF NOT EXISTS body_text TEXT,
            ADD COLUMN IF NOT EXISTS body_source_url TEXT,
            ADD COLUMN IF NOT EXISTS body_fetched_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS body_hash VARCHAR(64)
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        ALTER TABLE authority_index_items
            DROP COLUMN IF EXISTS body_text,
            DROP COLUMN IF EXISTS body_source_url,
            DROP COLUMN IF EXISTS body_fetched_at,
            DROP COLUMN IF EXISTS body_hash
        """
    )
