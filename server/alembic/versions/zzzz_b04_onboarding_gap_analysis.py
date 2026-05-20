"""Add gap_analysis JSONB to onboarding_sessions.

Revision ID: zzzz_b04_onb_gap
Revises: zzzz_b03_chmsg_cmid
Create Date: 2026-05-19

The admin onboarding wizard is a gap-analysis tool. Every input it
captures already lives on onboarding_sessions (basics, size, locations,
ai_scope, resolved_scope.{existing,missing,ambiguous,gap_check}), but
finalize only surfaces counts. This column holds the assembled,
frozen-at-finalize dossier snapshot — the durable deliverable the team
reviews + exports (PDF / markdown) to prepare for onboarding a
compliance-complex company.

Nullable: older sessions and in-progress sessions have no snapshot; the
report endpoint assembles live from the existing JSONB when this is NULL.
"""
from alembic import op


revision = "zzzz_b04_onb_gap"
down_revision = "zzzz_b03_chmsg_cmid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE onboarding_sessions
        ADD COLUMN IF NOT EXISTS gap_analysis JSONB
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE onboarding_sessions DROP COLUMN IF EXISTS gap_analysis")
