"""ensure all handbook tables and columns exist

Revision ID: l7m8n9o0p1q2
Revises: k6l7m8n9o0p1
Create Date: 2026-03-07
"""

from alembic import op


revision = "l7m8n9o0p1q2"
down_revision = "k6l7m8n9o0p1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_handbook_profiles (
            company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            legal_name VARCHAR(255) NOT NULL,
            dba VARCHAR(255),
            ceo_or_president VARCHAR(255) NOT NULL,
            headcount INTEGER,
            remote_workers BOOLEAN NOT NULL DEFAULT false,
            minors BOOLEAN NOT NULL DEFAULT false,
            tipped_employees BOOLEAN NOT NULL DEFAULT false,
            union_employees BOOLEAN NOT NULL DEFAULT false,
            federal_contracts BOOLEAN NOT NULL DEFAULT false,
            group_health_insurance BOOLEAN NOT NULL DEFAULT false,
            background_checks BOOLEAN NOT NULL DEFAULT false,
            hourly_employees BOOLEAN NOT NULL DEFAULT true,
            salaried_employees BOOLEAN NOT NULL DEFAULT false,
            commissioned_employees BOOLEAN NOT NULL DEFAULT false,
            tip_pooling BOOLEAN NOT NULL DEFAULT false,
            updated_by UUID REFERENCES users(id),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for col, typedef in [
        ("legal_name", "VARCHAR(255)"),
        ("dba", "VARCHAR(255)"),
        ("ceo_or_president", "VARCHAR(255)"),
        ("headcount", "INTEGER"),
        ("remote_workers", "BOOLEAN NOT NULL DEFAULT false"),
        ("minors", "BOOLEAN NOT NULL DEFAULT false"),
        ("tipped_employees", "BOOLEAN NOT NULL DEFAULT false"),
        ("union_employees", "BOOLEAN NOT NULL DEFAULT false"),
        ("federal_contracts", "BOOLEAN NOT NULL DEFAULT false"),
        ("group_health_insurance", "BOOLEAN NOT NULL DEFAULT false"),
        ("background_checks", "BOOLEAN NOT NULL DEFAULT false"),
        ("hourly_employees", "BOOLEAN NOT NULL DEFAULT true"),
        ("salaried_employees", "BOOLEAN NOT NULL DEFAULT false"),
        ("commissioned_employees", "BOOLEAN NOT NULL DEFAULT false"),
        ("tip_pooling", "BOOLEAN NOT NULL DEFAULT false"),
        ("updated_at", "TIMESTAMP DEFAULT NOW()"),
    ]:
        op.execute(f"ALTER TABLE company_handbook_profiles ADD COLUMN IF NOT EXISTS {col} {typedef}")
    op.execute("ALTER TABLE company_handbook_profiles ADD COLUMN IF NOT EXISTS updated_by UUID REFERENCES users(id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_company_handbook_profiles_company_id "
        "ON company_handbook_profiles(company_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbooks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title VARCHAR(500) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'archived')),
            mode VARCHAR(20) NOT NULL DEFAULT 'single_state'
                CHECK (mode IN ('single_state', 'multi_state')),
            source_type VARCHAR(20) NOT NULL DEFAULT 'template'
                CHECK (source_type IN ('template', 'upload')),
            active_version INTEGER NOT NULL DEFAULT 1,
            file_url VARCHAR(1000),
            file_name VARCHAR(255),
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            published_at TIMESTAMP
        )
    """)
    for col, typedef in [
        ("mode", "VARCHAR(20) NOT NULL DEFAULT 'single_state'"),
        ("source_type", "VARCHAR(20) NOT NULL DEFAULT 'template'"),
        ("active_version", "INTEGER NOT NULL DEFAULT 1"),
        ("file_url", "VARCHAR(1000)"),
        ("file_name", "VARCHAR(255)"),
        ("published_at", "TIMESTAMP"),
        ("guided_answers", "JSONB DEFAULT '{}'"),
    ]:
        op.execute(f"ALTER TABLE handbooks ADD COLUMN IF NOT EXISTS {col} {typedef}")
    op.execute("ALTER TABLE handbooks ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_handbooks_company_id ON handbooks(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_handbooks_status ON handbooks(status)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_handbooks_company_active "
        "ON handbooks(company_id) WHERE status = 'active'"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_wizard_drafts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            draft_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_handbook_wizard_drafts_company_user ON handbook_wizard_drafts(company_id, user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_versions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
            version_number INTEGER NOT NULL,
            summary TEXT,
            is_published BOOLEAN NOT NULL DEFAULT false,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(handbook_id, version_number)
        )
    """)
    for col, typedef in [
        ("summary", "TEXT"),
        ("is_published", "BOOLEAN NOT NULL DEFAULT false"),
    ]:
        op.execute(f"ALTER TABLE handbook_versions ADD COLUMN IF NOT EXISTS {col} {typedef}")
    op.execute("ALTER TABLE handbook_versions ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_handbook_versions_unique_version "
        "ON handbook_versions(handbook_id, version_number)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_handbook_versions_handbook_id ON handbook_versions(handbook_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_scopes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
            state VARCHAR(2) NOT NULL,
            city VARCHAR(100),
            zipcode VARCHAR(10),
            location_id UUID,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for col, typedef in [
        ("city", "VARCHAR(100)"),
        ("zipcode", "VARCHAR(10)"),
        ("location_id", "UUID"),
    ]:
        op.execute(f"ALTER TABLE handbook_scopes ADD COLUMN IF NOT EXISTS {col} {typedef}")
    op.execute("CREATE INDEX IF NOT EXISTS idx_handbook_scopes_handbook_id ON handbook_scopes(handbook_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_handbook_scopes_state ON handbook_scopes(state)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_sections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            handbook_version_id UUID NOT NULL REFERENCES handbook_versions(id) ON DELETE CASCADE,
            section_key VARCHAR(120) NOT NULL,
            title VARCHAR(255) NOT NULL,
            section_order INTEGER NOT NULL DEFAULT 0,
            section_type VARCHAR(20) NOT NULL DEFAULT 'core'
                CHECK (section_type IN ('core', 'state', 'custom', 'uploaded')),
            jurisdiction_scope JSONB DEFAULT '{}'::jsonb,
            content TEXT NOT NULL DEFAULT '',
            last_reviewed_at TIMESTAMPTZ,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(handbook_version_id, section_key)
        )
    """)
    for col, typedef in [
        ("section_order", "INTEGER NOT NULL DEFAULT 0"),
        ("section_type", "VARCHAR(20) NOT NULL DEFAULT 'core'"),
        ("jurisdiction_scope", "JSONB DEFAULT '{}'::jsonb"),
        ("last_reviewed_at", "TIMESTAMPTZ"),
    ]:
        op.execute(f"ALTER TABLE handbook_sections ADD COLUMN IF NOT EXISTS {col} {typedef}")
    op.execute("CREATE INDEX IF NOT EXISTS idx_handbook_sections_version_id ON handbook_sections(handbook_version_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_change_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
            handbook_version_id UUID NOT NULL REFERENCES handbook_versions(id) ON DELETE CASCADE,
            alert_id UUID,
            section_key VARCHAR(120),
            old_content TEXT,
            proposed_content TEXT NOT NULL,
            rationale TEXT,
            source_url VARCHAR(1000),
            effective_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'rejected')),
            resolved_by UUID REFERENCES users(id),
            resolved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_change_requests_handbook_id "
        "ON handbook_change_requests(handbook_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_change_requests_status "
        "ON handbook_change_requests(status)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_freshness_checks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            triggered_by UUID REFERENCES users(id),
            check_type VARCHAR(20) NOT NULL DEFAULT 'manual'
                CHECK (check_type IN ('manual', 'scheduled')),
            status VARCHAR(20) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'completed', 'failed')),
            is_outdated BOOLEAN NOT NULL DEFAULT false,
            impacted_sections INTEGER NOT NULL DEFAULT 0,
            changes_created INTEGER NOT NULL DEFAULT 0,
            requirements_fingerprint VARCHAR(128),
            previous_fingerprint VARCHAR(128),
            profile_fingerprint VARCHAR(128),
            requirements_last_updated_at TIMESTAMPTZ,
            data_staleness_days INTEGER,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute(
        "ALTER TABLE handbook_freshness_checks "
        "ADD COLUMN IF NOT EXISTS profile_fingerprint VARCHAR(128)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_freshness_checks_handbook_created "
        "ON handbook_freshness_checks(handbook_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_freshness_checks_company_created "
        "ON handbook_freshness_checks(company_id, created_at DESC)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_freshness_findings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            freshness_check_id UUID NOT NULL REFERENCES handbook_freshness_checks(id) ON DELETE CASCADE,
            handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
            section_key VARCHAR(120),
            finding_type VARCHAR(40) NOT NULL,
            summary TEXT NOT NULL,
            old_content TEXT,
            proposed_content TEXT,
            source_url VARCHAR(1000),
            effective_date DATE,
            age_days INTEGER,
            change_request_id UUID REFERENCES handbook_change_requests(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_freshness_findings_check "
        "ON handbook_freshness_findings(freshness_check_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_freshness_findings_handbook "
        "ON handbook_freshness_findings(handbook_id)"
    )
    op.execute(
        "ALTER TABLE handbook_freshness_findings "
        "ADD COLUMN IF NOT EXISTS age_days INTEGER"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS handbook_distribution_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
            handbook_version_id UUID NOT NULL REFERENCES handbook_versions(id) ON DELETE CASCADE,
            distributed_by UUID REFERENCES users(id),
            distributed_at TIMESTAMP DEFAULT NOW(),
            employee_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbook_distribution_runs_handbook_id "
        "ON handbook_distribution_runs(handbook_id)"
    )


def downgrade():
    # These tables may have existed before this migration; only drop if
    # you truly want to remove all handbook infrastructure.
    pass
