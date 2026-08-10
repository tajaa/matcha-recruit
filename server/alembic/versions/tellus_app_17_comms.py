"""Tellus Comms — consumer-initiated business conversations.

Extends the existing report-linked DM tables in place. Existing feedback
threads remain ``kind='feedback'``; new public conversations use
``kind='general'`` and may omit ``report_id``.

Revision ID: tellus_app_17
Revises: oceanlab_app_03
"""
from alembic import op


revision = "tellus_app_17"
down_revision = "oceanlab_app_03"
branch_labels = None
depends_on = None


def _constraint(name: str, sql: str) -> None:
    op.execute(
        f"""DO $$ BEGIN
            ALTER TABLE tellus_dm_threads ADD CONSTRAINT {name} {sql};
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$"""
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS messaging_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE tellus_brand_members ADD COLUMN IF NOT EXISTS can_manage_inbox BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "UPDATE tellus_brand_members SET can_manage_inbox = TRUE WHERE role = 'owner'"
    )

    op.execute("ALTER TABLE tellus_dm_threads ALTER COLUMN report_id DROP NOT NULL")
    op.execute("ALTER TABLE tellus_dm_threads ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'feedback'")
    op.execute("ALTER TABLE tellus_dm_threads ADD COLUMN IF NOT EXISTS store_id UUID REFERENCES tellus_stores(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE tellus_dm_threads ADD COLUMN IF NOT EXISTS topic TEXT")
    op.execute("ALTER TABLE tellus_dm_threads ADD COLUMN IF NOT EXISTS status TEXT")
    op.execute("ALTER TABLE tellus_dm_threads ADD COLUMN IF NOT EXISTS assigned_member_id UUID REFERENCES tellus_brand_members(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE tellus_dm_threads ADD COLUMN IF NOT EXISTS first_brand_response_at TIMESTAMPTZ")
    op.execute("ALTER TABLE tellus_dm_threads ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE tellus_dm_threads ADD COLUMN IF NOT EXISTS closed_by_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL")

    op.execute(
        """UPDATE tellus_dm_threads t
           SET store_id = r.store_id
          FROM tellus_reports r
         WHERE r.id = t.report_id AND t.store_id IS NULL"""
    )
    op.execute(
        """UPDATE tellus_dm_threads t
           SET status = CASE
               WHEN (SELECT m.sender_role FROM tellus_dm_messages m
                     WHERE m.thread_id = t.id
                     ORDER BY m.created_at DESC, m.id DESC LIMIT 1) = 'consumer'
               THEN 'waiting_brand' ELSE 'waiting_consumer' END
         WHERE t.status IS NULL"""
    )
    op.execute("ALTER TABLE tellus_dm_threads ALTER COLUMN status SET NOT NULL")

    _constraint("ck_tellus_dm_kind", "CHECK (kind IN ('feedback', 'general'))")
    _constraint(
        "ck_tellus_dm_status",
        "CHECK (status IN ('waiting_brand', 'waiting_consumer', 'closed'))",
    )
    _constraint(
        "ck_tellus_dm_topic",
        "CHECK (topic IS NULL OR topic IN ('hours', 'availability', 'inventory', 'order', 'service', 'accessibility', 'other'))",
    )
    _constraint(
        "ck_tellus_dm_kind_report",
        "CHECK ((kind = 'feedback' AND report_id IS NOT NULL) OR (kind = 'general' AND report_id IS NULL))",
    )
    _constraint(
        "ck_tellus_dm_closed_pair",
        "CHECK ((status = 'closed' AND closed_at IS NOT NULL) OR (status <> 'closed' AND closed_at IS NULL))",
    )

    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_dm_general_open_store ON tellus_dm_threads (brand_id, consumer_account_id, store_id) WHERE kind = 'general' AND status <> 'closed' AND store_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_dm_general_open_brand ON tellus_dm_threads (brand_id, consumer_account_id) WHERE kind = 'general' AND status <> 'closed' AND store_id IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_dm_threads_brand_status ON tellus_dm_threads (brand_id, status, last_message_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_dm_threads_assignee ON tellus_dm_threads (assigned_member_id, status, last_message_at DESC) WHERE assigned_member_id IS NOT NULL")

    op.execute("ALTER TABLE tellus_dm_messages ADD COLUMN IF NOT EXISTS client_message_id UUID")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_dm_message_client_id ON tellus_dm_messages (sender_account_id, client_message_id) WHERE client_message_id IS NOT NULL")


def downgrade() -> None:
    # General conversations have no report_id; a downgrade intentionally drops
    # these rows before restoring the legacy NOT NULL invariant.
    op.execute("DELETE FROM tellus_dm_threads WHERE kind = 'general'")
    op.execute("DROP INDEX IF EXISTS ux_tellus_dm_message_client_id")
    op.execute("ALTER TABLE tellus_dm_messages DROP COLUMN IF EXISTS client_message_id")
    op.execute("DROP INDEX IF EXISTS ux_tellus_dm_threads_assignee")
    op.execute("DROP INDEX IF EXISTS ix_tellus_dm_threads_brand_status")
    op.execute("DROP INDEX IF EXISTS ux_tellus_dm_general_open_brand")
    op.execute("DROP INDEX IF EXISTS ux_tellus_dm_general_open_store")
    for name in ("ck_tellus_dm_closed_pair", "ck_tellus_dm_kind_report", "ck_tellus_dm_topic", "ck_tellus_dm_status", "ck_tellus_dm_kind"):
        op.execute(f"ALTER TABLE tellus_dm_threads DROP CONSTRAINT IF EXISTS {name}")
    op.execute("ALTER TABLE tellus_dm_threads DROP COLUMN IF EXISTS closed_by_account_id")
    op.execute("ALTER TABLE tellus_dm_threads DROP COLUMN IF EXISTS closed_at")
    op.execute("ALTER TABLE tellus_dm_threads DROP COLUMN IF EXISTS first_brand_response_at")
    op.execute("ALTER TABLE tellus_dm_threads DROP COLUMN IF EXISTS assigned_member_id")
    op.execute("ALTER TABLE tellus_dm_threads DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE tellus_dm_threads DROP COLUMN IF EXISTS topic")
    op.execute("ALTER TABLE tellus_dm_threads DROP COLUMN IF EXISTS store_id")
    op.execute("ALTER TABLE tellus_dm_threads DROP COLUMN IF EXISTS kind")
    op.execute("ALTER TABLE tellus_dm_threads ALTER COLUMN report_id SET NOT NULL")
    op.execute("ALTER TABLE tellus_brand_members DROP COLUMN IF EXISTS can_manage_inbox")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS messaging_enabled")
