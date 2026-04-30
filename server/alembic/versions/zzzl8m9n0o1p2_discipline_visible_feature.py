"""Expose `discipline` in platform_settings.visible_features.

Backend `require_feature` (matcha/dependencies.py) double-gates anything
in `KNOWN_PLATFORM_ITEMS`: the per-company flag must be on AND the feature
key must appear in the platform-wide `visible_features` allowlist.
`discipline` was added to `KNOWN_PLATFORM_ITEMS` when the engine shipped
but never added to the allowlist, so every /api/discipline/* request
returns 403 "'discipline' is not currently available" even on companies
that explicitly enabled the flag.

Revision ID: zzzl8m9n0o1p2
Revises: zzzk7l8m9n0o1
Create Date: 2026-04-29
"""
from alembic import op


revision = "zzzl8m9n0o1p2"
down_revision = "zzzk7l8m9n0o1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO platform_settings (key, value)
        VALUES ('visible_features', '["discipline"]'::jsonb)
        ON CONFLICT (key) DO UPDATE
        SET value = CASE
            WHEN platform_settings.value ? 'discipline'
                THEN platform_settings.value
            ELSE platform_settings.value || '["discipline"]'::jsonb
        END,
        updated_at = NOW()
    """)


def downgrade():
    op.execute("""
        UPDATE platform_settings
        SET value = value - 'discipline',
            updated_at = NOW()
        WHERE key = 'visible_features'
    """)
