"""Add jurisdiction_requirements.implementation_steps — AI "how to comply" steps.

Phase 2 of the gap-analysis dashboard. When a gap is researched, Gemini now also
emits a short ordered list of concrete actions an employer takes to comply
("implementation_steps"). Stored as JSONB (array of strings) on the shared
requirement bank so the dashboard's covered-item drill-in can render the steps.

Nullable — pre-existing rows and any requirement researched before this column
existed simply have no steps until re-researched. Idempotent.

Revision ID: jrimplsteps01
Revises: mwsubround01
Create Date: 2026-05-28
"""
from alembic import op


revision = "jrimplsteps01"
down_revision = "mwsubround01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE jurisdiction_requirements "
        "ADD COLUMN IF NOT EXISTS implementation_steps JSONB"
    )


def downgrade():
    op.execute(
        "ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS implementation_steps"
    )
