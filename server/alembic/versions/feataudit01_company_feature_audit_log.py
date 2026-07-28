"""Add company_feature_audit_log — who/what/why changed a company's
enabled_features, going forward.

No provenance trail existed for enabled_features writes before this: the
admin toggle, tier changes, product sync/activate, and the Stripe webhook's
custom_product branch (which overwrites the WHOLE feature dict) all did bare
UPDATEs. /admin/company-features/{id}/provenance classifies each currently-
enabled feature as tier/add-on/custom-product/paid-gate where derivable from
current state, falling back to this log's latest row, and to an honest
"unknown origin (pre-audit)" bucket for anything neither can explain —
historical manual-toggle-vs-signup-time origin is genuinely unrecoverable and
this migration does not attempt to backfill it.

Revision ID: feataudit01
Revises: huume03
Create Date: 2026-07-28
"""
from alembic import op

revision = "feataudit01"
down_revision = "huume03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_feature_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            feature TEXT NOT NULL,
            old_value BOOLEAN,
            new_value BOOLEAN NOT NULL,
            source TEXT NOT NULL CHECK (source IN (
                'admin_toggle', 'tier_change', 'product_sync', 'stripe_webhook'
            )),
            actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_feature_audit_log_lookup
        ON company_feature_audit_log (company_id, feature, created_at DESC)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_feature_audit_log")
