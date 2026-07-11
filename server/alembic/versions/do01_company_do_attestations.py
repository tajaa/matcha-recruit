"""D&O / management-liability attestations.

Revision ID: do01
Revises: coi01
Create Date: 2026-07-11

Per-company attested D&O readiness factors (board governance, financial health,
ERISA/fiduciary, bankruptcy/M&A, prior claims). Mirrors company_epl_attestations.
"""

from alembic import op


revision = "do01"
down_revision = "coi01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_do_attestations (
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_key    VARCHAR(60) NOT NULL,
            status      VARCHAR(20) NOT NULL DEFAULT 'unknown'
                          CHECK (status IN ('in_place','partial','gap','unknown')),
            note        TEXT,
            updated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (company_id, item_key)
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_do_attestations")
