"""add handbook freshness check tables

Revision ID: k2l3m4n5o6p7
Revises: h9i0j1k2l3m4
Create Date: 2026-02-25
"""

from alembic import op


revision = "k2l3m4n5o6p7"
down_revision = "h9i0j1k2l3m4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
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
            requirements_last_updated_at TIMESTAMPTZ,
            data_staleness_days INTEGER,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_handbook_freshness_checks_handbook_created
        ON handbook_freshness_checks(handbook_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_handbook_freshness_checks_company_created
        ON handbook_freshness_checks(company_id, created_at DESC)
        """
    )

    op.execute(
        """
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
            change_request_id UUID REFERENCES handbook_change_requests(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_handbook_freshness_findings_check
        ON handbook_freshness_findings(freshness_check_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_handbook_freshness_findings_handbook
        ON handbook_freshness_findings(handbook_id)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_handbook_freshness_findings_handbook")
    op.execute("DROP INDEX IF EXISTS idx_handbook_freshness_findings_check")
    op.execute("DROP TABLE IF EXISTS handbook_freshness_findings")

    op.execute("DROP INDEX IF EXISTS idx_handbook_freshness_checks_company_created")
    op.execute("DROP INDEX IF EXISTS idx_handbook_freshness_checks_handbook_created")
    op.execute("DROP TABLE IF EXISTS handbook_freshness_checks")
