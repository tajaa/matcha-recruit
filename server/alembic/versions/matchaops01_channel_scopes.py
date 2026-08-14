"""Separate Matcha Ops channels from Matcha Work project discussions.

Existing non-personal companies with a non-project channel are grandfathered
into Matcha Ops. Personal channels remain community channels.
"""

from alembic import op


revision = "matchaops01"
down_revision = "ems04"
branch_labels = None
depends_on = ("inventory01", "proddef01", "v2w3x4y5z6a", "feataudit01")


def upgrade() -> None:
    op.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS channel_scope TEXT")
    op.execute(
        """
        UPDATE channels ch
           SET channel_scope = CASE
               WHEN c.is_personal IS TRUE THEN 'community'
               WHEN EXISTS (
                   SELECT 1 FROM mw_projects p
                    WHERE p.project_data->>'discussion_channel_id' = ch.id::text
               ) THEN 'project_discussion'
               ELSE 'operations'
           END
          FROM companies c
         WHERE c.id = ch.company_id
           AND ch.channel_scope IS NULL
        """
    )
    op.execute("ALTER TABLE channels ALTER COLUMN channel_scope SET DEFAULT 'operations'")
    op.execute("ALTER TABLE channels ALTER COLUMN channel_scope SET NOT NULL")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conname = 'channels_channel_scope_check'
            ) THEN
                ALTER TABLE channels ADD CONSTRAINT channels_channel_scope_check
                    CHECK (channel_scope IN ('operations', 'project_discussion', 'community'));
            END IF;
        END $$
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channels_company_scope
            ON channels(company_id, channel_scope, is_archived)
        """
    )

    # Preserve access for existing tenants that already use Ops capabilities
    # or own a business channel, without granting Ops to every Work tenant.
    op.execute(
        """
        UPDATE companies
           SET enabled_features = jsonb_set(
               COALESCE(enabled_features, '{}'::jsonb),
               '{matcha_ops_calls_all_members}',
               COALESCE(enabled_features->'werk_lite_calls_all_members', 'false'::jsonb),
               true
           )
         WHERE COALESCE((enabled_features->>'werk_lite_calls_all_members')::boolean, false)
        """
    )
    op.execute(
        """
        UPDATE product_definitions
           SET features = jsonb_set(COALESCE(features, '{}'::jsonb), '{matcha_ops}', 'true'::jsonb, true)
          WHERE COALESCE((features->>'matcha_ops')::boolean, false) IS NOT TRUE
           AND (
               COALESCE((features->>'ems')::boolean, false)
               OR COALESCE((features->>'inventory')::boolean, false)
               OR COALESCE((features->>'employee_schedule')::boolean, false)
               OR COALESCE((features->>'schedule_intelligence')::boolean, false)
               OR COALESCE((features->>'werk_lite')::boolean, false)
           )
        """
    )
    op.execute(
        """
        UPDATE broker_client_setups
           SET preconfigured_features = jsonb_set(
               COALESCE(preconfigured_features, '{}'::jsonb), '{matcha_ops}', 'true'::jsonb, true
           )
          WHERE COALESCE((preconfigured_features->>'matcha_ops')::boolean, false) IS NOT TRUE
            AND (
                COALESCE((preconfigured_features->>'ems')::boolean, false)
                OR COALESCE((preconfigured_features->>'inventory')::boolean, false)
                OR COALESCE((preconfigured_features->>'employee_schedule')::boolean, false)
                OR COALESCE((preconfigured_features->>'schedule_intelligence')::boolean, false)
                OR COALESCE((preconfigured_features->>'werk_lite')::boolean, false)
            )
        """
    )

    op.execute("ALTER TABLE company_feature_audit_log DROP CONSTRAINT IF EXISTS company_feature_audit_log_source_check")
    op.execute(
        """
        ALTER TABLE company_feature_audit_log
        ADD CONSTRAINT company_feature_audit_log_source_check CHECK (source IN (
            'admin_toggle', 'tier_change', 'product_sync', 'stripe_webhook',
            'migration_backfill'
        ))
        """
    )
    op.execute(
        """
        WITH changed AS (
            UPDATE companies c
               SET enabled_features = jsonb_set(
                   COALESCE(c.enabled_features, '{}'::jsonb),
                   '{matcha_ops}', 'true'::jsonb, true
               )
             WHERE c.is_personal IS NOT TRUE
               AND COALESCE((c.enabled_features->>'matcha_ops')::boolean, false) IS NOT TRUE
               AND (
                   COALESCE((c.enabled_features->>'ems')::boolean, false)
                   OR COALESCE((c.enabled_features->>'inventory')::boolean, false)
                   OR COALESCE((c.enabled_features->>'employee_schedule')::boolean, false)
                   OR COALESCE((c.enabled_features->>'schedule_intelligence')::boolean, false)
                   OR COALESCE((c.enabled_features->>'werk_lite')::boolean, false)
                   OR EXISTS (
                       SELECT 1 FROM channels ch
                        WHERE ch.company_id = c.id AND ch.channel_scope = 'operations'
                   )
               )
             RETURNING c.id
        )
        INSERT INTO company_feature_audit_log
            (company_id, feature, old_value, new_value, source)
        SELECT id, 'matcha_ops', false, true, 'migration_backfill'
          FROM changed
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channels_company_scope")
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_channel_scope_check")
    op.execute("ALTER TABLE channels DROP COLUMN IF EXISTS channel_scope")
