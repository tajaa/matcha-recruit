"""authority_index_drift: reviewed/acknowledged state

scopedrift01 made drift a review queue but left it append-only — no way to mark
a row handled, so the open queue could only ever grow. This adds the
acknowledge state:

  * status           — 'open' (default) | 'acknowledged'
  * acknowledged_by  — the admin who reviewed it
  * acknowledged_at  — when

Acknowledged rows are kept (audit trail + the `_record_drift` removed-dedupe
reads latest-row change_type regardless of status); the ScopeStudio queue
simply filters status='open'.

Not auto-applied — the user runs ./scripts/migrate-dev.sh / migrate-prod.sh.

Revision ID: scopedrift02
Revises: scopedrift01
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op


revision: str = "scopedrift02"
down_revision: Union[str, Sequence[str], None] = "scopedrift01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        ALTER TABLE authority_index_drift
            ADD COLUMN IF NOT EXISTS status VARCHAR(15) NOT NULL DEFAULT 'open',
            ADD COLUMN IF NOT EXISTS acknowledged_by UUID REFERENCES users(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP
        """
    )
    conn.exec_driver_sql(
        """
        DO $$ BEGIN
            ALTER TABLE authority_index_drift
                ADD CONSTRAINT ck_authority_index_drift_status
                CHECK (status IN ('open', 'acknowledged'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_authority_index_drift_status "
        "ON authority_index_drift(status) WHERE status = 'open'"
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "DROP INDEX IF EXISTS idx_authority_index_drift_status"
    )
    conn.exec_driver_sql(
        """
        ALTER TABLE authority_index_drift
            DROP CONSTRAINT IF EXISTS ck_authority_index_drift_status,
            DROP COLUMN IF EXISTS acknowledged_at,
            DROP COLUMN IF EXISTS acknowledged_by,
            DROP COLUMN IF EXISTS status
        """
    )
