"""cappe: domain reselling — registered/connected custom domains

cappe_domains tracks a tenant's purchased (Porkbun-registered) or connected
custom domain through its lifecycle:
  pending → (Stripe paid) → registering → active   (happy path)
                                       ↘ failed     (registration failed; refunded)
  active → expired (lapsed at renewal)

`cappe_sites.custom_domain` stays the live host-resolution pointer; a row here
is set active only once the domain is registered + DNS is pointed at the app.
Stripe fields are the PLATFORM charge (our revenue), not a Connect storefront sale.

Revision ID: zzzzcappe19
Revises: zzzzcappe18
Create Date: 2026-06-18
"""
from alembic import op

revision = "zzzzcappe19"
down_revision = "zzzzcappe18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_domains (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            domain VARCHAR(255) NOT NULL,
            -- 'register' = bought through us via Porkbun; 'connect' = tenant-owned, BYO.
            kind VARCHAR(16) NOT NULL DEFAULT 'register'
                CHECK (kind IN ('register','connect')),
            registrar VARCHAR(32) NOT NULL DEFAULT 'porkbun',
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','registering','active','failed','expired')),
            -- BYO 'connect' domains must prove control via a DNS TXT record before
            -- they go active (prevents claiming/squatting a domain you don't own).
            verification_token TEXT,
            -- Pricing snapshot (cents): what Porkbun charged us vs. what we charged the tenant.
            wholesale_cents INTEGER,
            retail_cents INTEGER,
            auto_renew BOOLEAN NOT NULL DEFAULT true,
            expires_at TIMESTAMPTZ,
            -- Platform Stripe charge (our account; NOT a Connect storefront sale).
            stripe_session_id TEXT,
            stripe_payment_intent TEXT,
            failure_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Only ONE active claim per domain — but multiple unverified/pending claims
    # are allowed, so a bogus pending claim can't block the real owner from
    # later verifying and activating the same domain.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS cappe_domains_active_domain_uniq "
        "ON cappe_domains(domain) WHERE status = 'active'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_domains_site ON cappe_domains(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_domains_account ON cappe_domains(account_id)")
    # Renewal sweep finds active domains by expiry.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_domains_renewal "
        "ON cappe_domains(expires_at) WHERE status = 'active' AND auto_renew"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_domains")
