"""cappe: 2026-09 audit hardening — scheduler rows, subscriber double opt-in,
domain edge (CloudFront tenant) tracking, campaign failure counts.

Set-based DDL/DML only; every statement is idempotent so a re-run is a no-op.

- scheduler_settings: rows for `cappe_domain_renewals` (dispatched by the worker
  since zzzzcappe20 but never seeded — it could not be enabled from the admin
  UI, which has no INSERT path), `cappe_order_reaper` (abandoned pending
  orders → cancel + restock) and `cappe_edge_sync` (custom-domain CloudFront
  tenant / certificate polling). All default OFF like every scheduled task.
- cappe_subscribers: `confirm_token` + `confirm_sent_at` + `pending_confirmation` status so
  owner-imported contacts are not mailed until they confirm.
- cappe_campaigns: `failed_count` so a partially failed blast is visible.
- cappe_domains: `transfer_requested` status; CloudFront tenant columns
  (`cf_tenant_id`, `cf_routing_endpoint`, `edge_status`, `edge_error`,
  `edge_checked_at`); case-insensitive uniqueness on active domains.

Revision ID: zzzzcappe31
Revises: sconboard01
Create Date: 2026-09-17
"""

from alembic import op

revision = "zzzzcappe31"
down_revision = "sconboard01"
branch_labels = None
depends_on = None


# Inline CHECK constraints from CREATE TABLE carry auto-generated names
# (`<table>_status_check` on every Postgres we run, but never assume) — look the
# name up from pg_constraint before dropping, same as zzzzcappe12 did for the
# availability UNIQUE.
_DROP_STATUS_CHECK = """
DO $$
DECLARE c text;
BEGIN
    SELECT conname INTO c
      FROM pg_constraint
     WHERE conrelid = '{table}'::regclass
       AND contype = 'c'
       AND pg_get_constraintdef(oid) LIKE '%(status)%';
    IF c IS NOT NULL THEN
        EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', c);
    END IF;
END $$;
"""


def upgrade() -> None:
    # ── scheduler rows ──────────────────────────────────────────────────────
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES
        ('cappe_domain_renewals', 'Cappe Domain Renewals',
         'Charge tenants for domains expiring within 14 days; lapse non-payers.', false, 50),
        ('cappe_order_reaper', 'Cappe Order Reaper',
         'Cancel + restock storefront orders left pending after Stripe Checkout was abandoned.', false, 100),
        ('cappe_edge_sync', 'Cappe Edge Sync',
         'Poll CloudFront distribution tenants for custom domains; go live when the certificate is issued.', false, 50)
        ON CONFLICT (task_key) DO NOTHING
    """)

    # ── subscribers: double opt-in for imported contacts ───────────────────
    op.execute("ALTER TABLE cappe_subscribers ADD COLUMN IF NOT EXISTS confirm_token UUID")
    # Claim-before-send marker for the confirmation worker: a confirmation is
    # mailed at most once, and one the worker died before sending is picked up
    # again instead of being lost with an in-process task.
    op.execute("ALTER TABLE cappe_subscribers ADD COLUMN IF NOT EXISTS confirm_sent_at TIMESTAMPTZ")
    op.execute(_DROP_STATUS_CHECK.format(table="cappe_subscribers"))
    op.execute("""
        ALTER TABLE cappe_subscribers ADD CONSTRAINT cappe_subscribers_status_check
        CHECK (status IN ('subscribed', 'unsubscribed', 'bounced', 'pending', 'pending_confirmation'))
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_subscribers_confirm_token "
        "ON cappe_subscribers (confirm_token) WHERE confirm_token IS NOT NULL"
    )

    # ── campaigns: partial-failure visibility ──────────────────────────────
    op.execute(
        "ALTER TABLE cappe_campaigns ADD COLUMN IF NOT EXISTS failed_count INTEGER NOT NULL DEFAULT 0"
    )

    # ── domains: transfer-out status + CloudFront tenant tracking ──────────
    op.execute(_DROP_STATUS_CHECK.format(table="cappe_domains"))
    op.execute("""
        ALTER TABLE cappe_domains ADD CONSTRAINT cappe_domains_status_check
        CHECK (status IN ('pending', 'registering', 'active', 'failed', 'expired', 'transfer_requested'))
    """)
    op.execute("""
        ALTER TABLE cappe_domains
            ADD COLUMN IF NOT EXISTS cf_tenant_id TEXT,
            ADD COLUMN IF NOT EXISTS cf_routing_endpoint TEXT,
            ADD COLUMN IF NOT EXISTS edge_status VARCHAR(16) NOT NULL DEFAULT 'none',
            ADD COLUMN IF NOT EXISTS edge_error TEXT,
            ADD COLUMN IF NOT EXISTS edge_checked_at TIMESTAMPTZ
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conrelid = 'cappe_domains'::regclass AND conname = 'cappe_domains_edge_status_check'
            ) THEN
                ALTER TABLE cappe_domains ADD CONSTRAINT cappe_domains_edge_status_check
                    CHECK (edge_status IN ('none', 'provisioning', 'pending_dns', 'live', 'failed'));
            END IF;
        END $$;
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_domains_edge_pending "
        "ON cappe_domains (edge_status) WHERE edge_status IN ('provisioning', 'pending_dns')"
    )
    # Domains are lowercased on every write path (normalize_custom_domain), so
    # this only ever touches rows written before that validator existed.
    op.execute("UPDATE cappe_domains SET domain = lower(domain) WHERE domain <> lower(domain)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_domains_lower_active "
        "ON cappe_domains (lower(domain)) WHERE status = 'active'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_cappe_domains_lower_active")
    op.execute("DROP INDEX IF EXISTS idx_cappe_domains_edge_pending")
    op.execute("ALTER TABLE cappe_domains DROP CONSTRAINT IF EXISTS cappe_domains_edge_status_check")
    op.execute("""
        ALTER TABLE cappe_domains
            DROP COLUMN IF EXISTS edge_checked_at,
            DROP COLUMN IF EXISTS edge_error,
            DROP COLUMN IF EXISTS edge_status,
            DROP COLUMN IF EXISTS cf_routing_endpoint,
            DROP COLUMN IF EXISTS cf_tenant_id
    """)
    # Fold the new status back before narrowing the CHECK (a transfer request
    # is a flag on an otherwise active registration).
    op.execute("UPDATE cappe_domains SET status = 'active' WHERE status = 'transfer_requested'")
    op.execute(_DROP_STATUS_CHECK.format(table="cappe_domains"))
    op.execute("""
        ALTER TABLE cappe_domains ADD CONSTRAINT cappe_domains_status_check
        CHECK (status IN ('pending', 'registering', 'active', 'failed', 'expired'))
    """)

    op.execute("ALTER TABLE cappe_campaigns DROP COLUMN IF EXISTS failed_count")

    op.execute("DROP INDEX IF EXISTS idx_cappe_subscribers_confirm_token")
    op.execute("UPDATE cappe_subscribers SET status = 'pending' WHERE status = 'pending_confirmation'")
    op.execute(_DROP_STATUS_CHECK.format(table="cappe_subscribers"))
    op.execute("""
        ALTER TABLE cappe_subscribers ADD CONSTRAINT cappe_subscribers_status_check
        CHECK (status IN ('subscribed', 'unsubscribed', 'bounced', 'pending'))
    """)
    op.execute("ALTER TABLE cappe_subscribers DROP COLUMN IF EXISTS confirm_sent_at")
    op.execute("ALTER TABLE cappe_subscribers DROP COLUMN IF EXISTS confirm_token")

    op.execute(
        "DELETE FROM scheduler_settings "
        "WHERE task_key IN ('cappe_domain_renewals', 'cappe_order_reaper', 'cappe_edge_sync')"
    )
