"""add sales-pipeline fields to mw_tasks

Revision ID: salespipe0001
Revises: 50268295866e
Create Date: 2026-05-21

Adds optional deal / contact / outcome / follow-up columns to mw_tasks so a
collab kanban board running in "pipeline mode" can track sales deals. All
columns are nullable and additive (ADD COLUMN IF NOT EXISTS) — safe,
reversible, and a no-op for normal (non-sales) boards which simply leave
them NULL. The pipeline-mode toggle itself lives in mw_projects.project_data
(JSONB, no schema change).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "salespipe0001"
down_revision: Union[str, Sequence[str], None] = "50268295866e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mw_tasks
            ADD COLUMN IF NOT EXISTS deal_value      NUMERIC(14,2),
            ADD COLUMN IF NOT EXISTS probability     SMALLINT,
            ADD COLUMN IF NOT EXISTS contact_name    TEXT,
            ADD COLUMN IF NOT EXISTS contact_company TEXT,
            ADD COLUMN IF NOT EXISTS contact_email   TEXT,
            ADD COLUMN IF NOT EXISTS contact_phone   TEXT,
            ADD COLUMN IF NOT EXISTS outcome         VARCHAR(10),
            ADD COLUMN IF NOT EXISTS loss_reason     TEXT,
            ADD COLUMN IF NOT EXISTS next_action_at  DATE,
            ADD COLUMN IF NOT EXISTS expected_close  DATE
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE mw_tasks
            DROP COLUMN IF EXISTS deal_value,
            DROP COLUMN IF EXISTS probability,
            DROP COLUMN IF EXISTS contact_name,
            DROP COLUMN IF EXISTS contact_company,
            DROP COLUMN IF EXISTS contact_email,
            DROP COLUMN IF EXISTS contact_phone,
            DROP COLUMN IF EXISTS outcome,
            DROP COLUMN IF EXISTS loss_reason,
            DROP COLUMN IF EXISTS next_action_at,
            DROP COLUMN IF EXISTS expected_close
        """
    )
