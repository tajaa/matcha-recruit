"""Merge the three open alembic heads before the risk-extension tables.

Revision ID: riskext00
Revises: zzzzcappe21, baseline01, mvrtype01
Create Date: 2026-07-11

The tree had diverged into three heads (cappe style presets, labor baseline
keys, and the mvr_review_type widen). Unify them so the risk-extension tables
(tcor01 → coi01 → do01) chain onto a single head. No-op merge.
"""

from alembic import op  # noqa: F401


revision = "riskext00"
down_revision = ("zzzzcappe21", "baseline01", "mvrtype01")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
