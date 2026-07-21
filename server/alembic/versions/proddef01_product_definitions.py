"""Admin-composable product definitions (the /admin/products builder).

Revision ID: proddef01
Revises: irshare01
Create Date: 2026-07-21

Every sellable product today (Lite, Essentials, X, Compliance, Pro) is ~10
hardcoded touchpoints: a signup_source string, a TIER_REQUIRED_FEATURES
overlay, an auth.py register branch, a _TIER_FEATURE_PRESETS row, a
matcha_lite_pricing row, a dedicated /resources/checkout/<x> endpoint, a
stripe-webhook branch, tier.ts predicates, a pending sidebar and an active
sidebar. Shipping a package is a code project.

This table makes NEW packages data: the admin picks feature flags, a paid
gate, a pricing model, and gets a shareable /p/<slug>/signup URL. Tenants who
sign up land on signup_source = 'product:<slug>' — the prefix guarantees no
collision with the existing hardcoded sources, and an unknown source is
already a no-op in merge_company_features' TIER_REQUIRED_FEATURES lookup.

Feature grants are MATERIALIZED into companies.enabled_features at
signup/payment rather than overlaid at read time: merge_company_features is
pure + sync and runs in the pool-free Celery workers, so a DB-consulting
overlay would need a cache on the hot path of every request. Editing a live
product therefore doesn't retro-grant — POST /admin/products/{id}/sync-tenants
re-materializes deliberately.

History table mirrors matcha_lite_pricing_history: this row sets what
customers are charged, so every change is snapshotted in the same transaction.

Fully reversible.
"""

from alembic import op


revision = "proddef01"
down_revision = "irshare01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_definitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            -- {"incidents": true, ...} — the flags written into
            -- companies.enabled_features on activation. Validated against the
            -- DEFAULT_COMPANY_FEATURES whitelist in the service layer.
            features JSONB NOT NULL DEFAULT '{}'::jsonb,
            -- The paid gate: the one flag that is false while payment is
            -- pending and true once the Stripe webhook fires (same role
            -- `incidents` plays for Lite and `compliance` for Compliance).
            -- NULL only for free / contact_sales products.
            gate_feature TEXT,
            pricing_model TEXT NOT NULL
                CHECK (pricing_model IN ('per_seat', 'block', 'flat', 'free', 'contact_sales')),
            -- Cents: per seat (per_seat), per block (block), or total (flat).
            price_cents INTEGER,
            block_size INTEGER,
            min_headcount INTEGER NOT NULL DEFAULT 1,
            max_headcount INTEGER NOT NULL DEFAULT 300,
            -- Ordered nav override: [{"feature": "incidents", "label": "..."}].
            -- NULL = derive from `features` in catalog order.
            nav JSONB,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'archived')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_definitions_status ON product_definitions(status)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_definition_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_id UUID NOT NULL REFERENCES product_definitions(id) ON DELETE CASCADE,
            snapshot JSONB NOT NULL,
            changed_by TEXT,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_definition_history_product "
        "ON product_definition_history(product_id, changed_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS product_definition_history")
    op.execute("DROP TABLE IF EXISTS product_definitions")
