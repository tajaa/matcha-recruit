"""cappe: saved style presets (reusable theme + section design)

A per-account library of saved looks:
- kind='theme'   → a `theme_config` style subset (style/type/colors/etc) the user
  can apply to any site.
- kind='section' → a block `_design` bag the user can drop onto any section.

Account-scoped, cascade-deleted with the account. Additive; no existing table
touched.

Revision ID: zzzzcappe21
Revises: zzzzcappe20
Create Date: 2026-07-11
"""
from alembic import op

revision = "zzzzcappe21"
down_revision = "zzzzcappe20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_style_presets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            name VARCHAR(80) NOT NULL,
            kind VARCHAR(16) NOT NULL CHECK (kind IN ('theme', 'section')),
            data JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_style_presets_account "
        "ON cappe_style_presets(account_id, kind)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_style_presets")
