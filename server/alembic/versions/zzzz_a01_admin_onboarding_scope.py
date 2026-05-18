"""Master-admin onboarding wizard + per-company compliance scope manifest.

Adds the schema described in ADMIN_ONBOARDING_WIZARD_PLAN.md (v2):

  - onboarding_sessions     — wizard run state (resumeable, idempotent)
  - company_compliance_scope — durable per-company manifest of requirement
                               IDs into the shared jurisdiction_requirements
                               bank. NEVER stores requirement text; pointers
                               only. UNIQUE on (company, requirement, location).
  - certifications_catalog  + company_certifications — promoted to phase 1
  - licenses_catalog        + company_licenses       — same shape, separate
                               table to preserve the cert/license semantic
                               distinction.

Plus business_locations gets:
  - is_company_wide BOOLEAN flag (and city/state/zipcode go nullable) so we
    can persist a synthetic "company-wide" sentinel for federal-only
    requirements without an FK pivot table. The wizard creates ONE
    sentinel row per company; federal scope rows attach to it.

Revision ID: zzzz_a01_aoscope
Revises:     zzzz9h0i1j2k3
Create Date: 2026-05-17
"""
from alembic import op


revision = "zzzz_a01_aoscope"
down_revision = "zzzz9h0i1j2k3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── business_locations: relax NOT NULL + add company-wide sentinel flag ──
    op.execute("""
        ALTER TABLE business_locations ALTER COLUMN city DROP NOT NULL
    """)
    op.execute("""
        ALTER TABLE business_locations ALTER COLUMN state DROP NOT NULL
    """)
    op.execute("""
        ALTER TABLE business_locations ALTER COLUMN zipcode DROP NOT NULL
    """)
    op.execute("""
        ALTER TABLE business_locations
        ADD COLUMN IF NOT EXISTS is_company_wide BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_business_locations_company_wide
            ON business_locations(company_id)
            WHERE is_company_wide = TRUE
    """)

    # ── onboarding_sessions ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_sessions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            schema_version  INT  NOT NULL DEFAULT 1,
            created_by      UUID NOT NULL REFERENCES users(id),
            company_id      UUID REFERENCES companies(id),
            owner_email     TEXT,
            owner_user_id   UUID REFERENCES users(id),
            invite_token    TEXT,
            idempotency_key TEXT UNIQUE,
            step            TEXT NOT NULL DEFAULT 'basics',
            basics          JSONB NOT NULL DEFAULT '{}'::jsonb,
            size            JSONB NOT NULL DEFAULT '{}'::jsonb,
            locations       JSONB NOT NULL DEFAULT '[]'::jsonb,
            ai_scope        JSONB,
            resolved_scope  JSONB,
            status          TEXT NOT NULL DEFAULT 'in_progress',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_created_by
            ON onboarding_sessions(created_by)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_company_id
            ON onboarding_sessions(company_id)
            WHERE company_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_status
            ON onboarding_sessions(status, updated_at DESC)
    """)

    # ── company_compliance_scope ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_compliance_scope (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            requirement_id    UUID NOT NULL REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            location_id       UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            scope_level       TEXT NOT NULL,
            source            TEXT NOT NULL DEFAULT 'onboarding_wizard',
            status            TEXT NOT NULL DEFAULT 'active',
            admin_reviewed_by UUID REFERENCES users(id),
            added_at          TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, requirement_id, location_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_scope_company
            ON company_compliance_scope(company_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_scope_requirement
            ON company_compliance_scope(requirement_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_scope_location
            ON company_compliance_scope(location_id)
    """)

    # ── certifications_catalog ───────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS certifications_catalog (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug              TEXT UNIQUE NOT NULL,
            name              TEXT NOT NULL,
            issuing_authority TEXT,
            scope_level       TEXT NOT NULL,
            industry_tag      TEXT,
            renewal_months    INT,
            description       TEXT,
            source_url        TEXT,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_certifications_catalog_industry
            ON certifications_catalog(industry_tag)
            WHERE industry_tag IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS company_certifications (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            certification_id UUID NOT NULL REFERENCES certifications_catalog(id),
            location_id      UUID REFERENCES business_locations(id) ON DELETE CASCADE,
            source           TEXT NOT NULL DEFAULT 'onboarding_wizard',
            status           TEXT NOT NULL DEFAULT 'required',
            added_at         TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, certification_id, location_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_certifications_company
            ON company_certifications(company_id)
    """)

    # ── licenses_catalog ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS licenses_catalog (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug              TEXT UNIQUE NOT NULL,
            name              TEXT NOT NULL,
            issuing_authority TEXT,
            scope_level       TEXT NOT NULL,
            industry_tag      TEXT,
            renewal_months    INT,
            description       TEXT,
            source_url        TEXT,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_licenses_catalog_industry
            ON licenses_catalog(industry_tag)
            WHERE industry_tag IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS company_licenses (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            license_id  UUID NOT NULL REFERENCES licenses_catalog(id),
            location_id UUID REFERENCES business_locations(id) ON DELETE CASCADE,
            source      TEXT NOT NULL DEFAULT 'onboarding_wizard',
            status      TEXT NOT NULL DEFAULT 'required',
            added_at    TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, license_id, location_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_licenses_company
            ON company_licenses(company_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_licenses")
    op.execute("DROP TABLE IF EXISTS licenses_catalog")
    op.execute("DROP TABLE IF EXISTS company_certifications")
    op.execute("DROP TABLE IF EXISTS certifications_catalog")
    op.execute("DROP TABLE IF EXISTS company_compliance_scope")
    op.execute("DROP TABLE IF EXISTS onboarding_sessions")
    op.execute("DROP INDEX IF EXISTS idx_business_locations_company_wide")
    op.execute("ALTER TABLE business_locations DROP COLUMN IF EXISTS is_company_wide")
    op.execute("ALTER TABLE business_locations ALTER COLUMN city SET NOT NULL")
    op.execute("ALTER TABLE business_locations ALTER COLUMN state SET NOT NULL")
    op.execute("ALTER TABLE business_locations ALTER COLUMN zipcode SET NOT NULL")
