"""Add Cappe website-builder tables.

Cappe is a separate product that runs on the matcha stack but does NOT use
matcha's tenant model. Its identity lives in `cappe_accounts` (its own
email/password), and account-scoped data (`cappe_sites`, `cappe_pages`) FKs to
that — never to `companies`/`clients`. `cappe_templates` is a platform-owned,
seeded catalog (not account-scoped) that sites clone from.

Revision ID: zzzzcappe01
Revises: mwjrnlrls01
Create Date: 2026-06-11
"""
from alembic import op


revision = "zzzzcappe01"
down_revision = "mwjrnlrls01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cappe identity/owner — mirrors `users` but a fully separate table so a
    # Cappe account is never coupled to a matcha company.
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(320) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(255),
            plan VARCHAR(20) NOT NULL DEFAULT 'free'
                CHECK (plan IN ('free', 'hosting', 'pro', 'business')),
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'suspended', 'deleted')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # Case-insensitive uniqueness so 'A@x.com' and 'a@x.com' can't both sign up
    # (login lower()-matches the email, mirroring core auth).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_accounts_email_lower "
        "ON cappe_accounts (lower(email))"
    )

    # Platform-owned template catalog. NOT account-scoped — seeded centrally and
    # cloned into a site on creation. `structure` holds the pages + blocks.
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(160) NOT NULL UNIQUE,
            category VARCHAR(60) NOT NULL DEFAULT 'general',
            description TEXT,
            preview_image_url TEXT,
            structure JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_premium BOOLEAN NOT NULL DEFAULT false,
            price_cents INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_templates_active ON cappe_templates(is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_templates_category ON cappe_templates(category)")

    # A user's website. account-scoped. `custom_domain` is the BYO field;
    # `subdomain` is the auto-assigned hosting handle. source_type records how
    # the site was started.
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_sites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(160) NOT NULL UNIQUE,
            subdomain VARCHAR(160) UNIQUE,
            custom_domain VARCHAR(255) UNIQUE,
            source_type VARCHAR(20) NOT NULL DEFAULT 'blank'
                CHECK (source_type IN ('template', 'byo', 'blank')),
            template_id UUID REFERENCES cappe_templates(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'archived')),
            theme_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            meta_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            published_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_sites_account ON cappe_sites(account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_sites_account_status ON cappe_sites(account_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_sites_template ON cappe_sites(template_id)")

    # Pages within a site. slug unique per-site.
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_pages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            slug VARCHAR(160) NOT NULL,
            content JSONB NOT NULL DEFAULT '{}'::jsonb,
            sort_order INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'archived')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (site_id, slug)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_pages_site ON cappe_pages(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_pages_site_status ON cappe_pages(site_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_pages_site_sort ON cappe_pages(site_id, sort_order)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_pages")
    op.execute("DROP TABLE IF EXISTS cappe_sites")
    op.execute("DROP TABLE IF EXISTS cappe_templates")
    op.execute("DROP TABLE IF EXISTS cappe_accounts")
