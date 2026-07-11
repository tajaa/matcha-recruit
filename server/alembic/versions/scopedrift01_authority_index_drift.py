"""scope registry: authority_index_drift — the "a federal law changed" log

`authority_ingest` is idempotent but was diff-blind: a re-ingest silently added
a new CFR section, updated an amended one's date, and left a repealed one in
place — no reviewable "what changed since last sweep" signal. This table
captures that diff, one row per change, written by `_record_drift` inside the
ingest transaction (before the item upsert, so it reads the prior snapshot as
baseline). It is the new-federal-law / policy-change detector.

`change_type`:
  * new      — citation absent from the previous ingest
  * amended  — heading or amendment_date changed
  * removed  — citation vanished upstream (recorded only; the item row is NOT
               deleted — orphan removal stays deferred)

Sibling of the `scoperg01` scope-registry tables (migration-only, not in
init_db) — chains off `srcstatus01` to keep this branch's history linear.

Not auto-applied — the user runs ./scripts/migrate-dev.sh / migrate-prod.sh.

Revision ID: scopedrift01
Revises: srcstatus01
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op


revision: str = "scopedrift01"
down_revision: Union[str, Sequence[str], None] = "srcstatus01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS authority_index_drift (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            authority_index_id UUID NOT NULL
                REFERENCES authority_indexes(id) ON DELETE CASCADE,
            change_type VARCHAR(10) NOT NULL
                CHECK (change_type IN ('new', 'amended', 'removed')),
            citation TEXT NOT NULL,
            heading TEXT,
            old_amendment_date DATE,
            new_amendment_date DATE,
            detected_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_authority_index_drift_index "
        "ON authority_index_drift(authority_index_id, detected_at DESC)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_authority_index_drift_type "
        "ON authority_index_drift(change_type)"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS authority_index_drift")
