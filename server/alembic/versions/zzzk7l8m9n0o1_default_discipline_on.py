"""Default the `discipline` feature flag to ON for existing companies.

Discipline (progressive discipline + DocuSeal signatures) is a standard
Platform feature for businesses, not an opt-in extra. The default in
`feature_flags.DEFAULT_COMPANY_FEATURES` flipped to True in the same
change, but rows created before that flip have `discipline: false`
baked into their `enabled_features` jsonb. Backfill them so the sidebar
entry actually renders.

Cap signups (`signup_source = 'ir_only_self_serve'`) already enable
discipline at register time, so this is effectively a no-op for them.

Revision ID: zzzk7l8m9n0o1
Revises: zzzj6k7l8m9n0
Create Date: 2026-04-29
"""
from alembic import op


revision = "zzzk7l8m9n0o1"
down_revision = "zzzj6k7l8m9n0"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Backfill per-company flag for business tenants on the full Platform —
    #    bespoke / invite / broker / legacy-null. Skip:
    #      - resources_free: signup explicitly bakes every flag False
    #      - ir_only_self_serve: already enables discipline at signup, no-op
    #      - is_personal = true: personal workspaces don't surface HR Ops
    op.execute("""
        UPDATE companies
        SET enabled_features = jsonb_set(
            COALESCE(enabled_features, '{}'::jsonb),
            '{discipline}',
            'true'::jsonb,
            true
        )
        WHERE COALESCE(is_personal, false) = false
          AND (signup_source IS NULL
               OR signup_source IN ('bespoke', 'invite', 'broker'))
    """)

    # 2. Add `discipline` to the platform-wide visibility allowlist so the
    #    `require_feature` backend gate (matcha/dependencies.py) stops 403'ing.
    #    `discipline` is in KNOWN_PLATFORM_ITEMS, which means the gate also
    #    requires it to live in platform_settings.visible_features. Without
    #    this, every /api/discipline/* request returns
    #    "'discipline' is not currently available".
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
        UPDATE companies
        SET enabled_features = jsonb_set(
            COALESCE(enabled_features, '{}'::jsonb),
            '{discipline}',
            'false'::jsonb,
            true
        )
        WHERE COALESCE(is_personal, false) = false
          AND (signup_source IS NULL
               OR signup_source IN ('bespoke', 'invite', 'broker'))
    """)

    op.execute("""
        UPDATE platform_settings
        SET value = value - 'discipline',
            updated_at = NOW()
        WHERE key = 'visible_features'
    """)
