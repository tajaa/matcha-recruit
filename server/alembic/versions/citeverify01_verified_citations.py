"""jurisdiction_requirements: registry-verified statute citations + drift propagation

The bridge between the Gemini-populated catalog and the authority registry.
`statute_citation` existed (VARCHAR(500), migration 04) but had no write path —
Gemini never emitted it, so 2667/2729 rows were NULL. This adds the columns that
let a citation be *verified by construction*: stamped only from the registry
linkage (a confirmed classification's authority_index_item), never from model
free-recall.

  * citation_verified_at  — when the registry stamped this citation. NULL = the
                            citation is unverified (hand-curated or model-derived),
                            not broken. Verified = statute_citation IS NOT NULL
                            AND citation_verified_at IS NOT NULL.
  * citation_item_id       — which authority_index_item is the primary citation
                            (powers the statute-reader link + drift joins without
                            re-deriving through scope_codifications).

authority_index_drift gains:
  * propagated_at          — when this drift row was fanned out to affected
                            jurisdiction_requirements (change_status='needs_review').
                            NULL = not yet propagated (the propagator's worklist).

Not auto-applied — the user runs ./scripts/migrate-dev.sh / migrate-prod.sh.

Revision ID: citeverify01
Revises: scopedrift02
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op


revision: str = "citeverify01"
down_revision: Union[str, Sequence[str], None] = "scopedrift02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS citation_verified_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS citation_item_id UUID
                REFERENCES authority_index_items(id) ON DELETE SET NULL
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_jr_citation_item "
        "ON jurisdiction_requirements(citation_item_id) WHERE citation_item_id IS NOT NULL"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_jr_needs_review "
        "ON jurisdiction_requirements(change_status) WHERE change_status = 'needs_review'"
    )
    conn.exec_driver_sql(
        "ALTER TABLE authority_index_drift "
        "ADD COLUMN IF NOT EXISTS propagated_at TIMESTAMP"
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "ALTER TABLE authority_index_drift DROP COLUMN IF EXISTS propagated_at"
    )
    conn.exec_driver_sql("DROP INDEX IF EXISTS idx_jr_needs_review")
    conn.exec_driver_sql("DROP INDEX IF EXISTS idx_jr_citation_item")
    conn.exec_driver_sql(
        """
        ALTER TABLE jurisdiction_requirements
            DROP COLUMN IF EXISTS citation_item_id,
            DROP COLUMN IF EXISTS citation_verified_at
        """
    )
