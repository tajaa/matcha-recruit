"""add provisioning tables for Google Workspace onboarding

Revision ID: x4y5z6a7b8c
Revises: w3x4y5z6a7b
Create Date: 2026-02-17
"""

from alembic import op


revision = "x4y5z6a7b8c"
down_revision = "w3x4y5z6a7b"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL
                CHECK (provider IN ('google_workspace', 'slack')),
            status VARCHAR(20) NOT NULL DEFAULT 'disconnected'
                CHECK (status IN ('disconnected', 'connected', 'error', 'needs_action')),
            config JSONB DEFAULT '{}'::jsonb,
            secrets JSONB DEFAULT '{}'::jsonb,
            last_tested_at TIMESTAMPTZ,
            last_error TEXT,
            created_by UUID REFERENCES users(id),
            updated_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (company_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_integration_connections_company_provider
        ON integration_connections(company_id, provider)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_integration_connections_status
        ON integration_connections(status)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS onboarding_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL
                CHECK (provider IN ('google_workspace', 'slack')),
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed', 'needs_action', 'rolled_back', 'cancelled')),
            trigger_source VARCHAR(30) NOT NULL DEFAULT 'manual'
                CHECK (trigger_source IN ('manual', 'employee_create', 'scheduled', 'retry', 'api')),
            triggered_by UUID REFERENCES users(id),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            last_error TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_onboarding_runs_company_provider_status
        ON onboarding_runs(company_id, provider, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_onboarding_runs_employee_provider
        ON onboarding_runs(employee_id, provider, created_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS onboarding_steps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES onboarding_runs(id) ON DELETE CASCADE,
            step_key VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed', 'needs_action', 'rolled_back', 'cancelled')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            last_response JSONB DEFAULT '{}'::jsonb,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (run_id, step_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_onboarding_steps_run_status
        ON onboarding_steps(run_id, status)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_identities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL
                CHECK (provider IN ('google_workspace', 'slack')),
            external_user_id VARCHAR(255),
            external_email VARCHAR(320),
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'suspended', 'deprovisioned', 'error')),
            raw_profile JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (employee_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_identities_company_provider
        ON external_identities(company_id, provider)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS provisioning_audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID REFERENCES employees(id) ON DELETE SET NULL,
            run_id UUID REFERENCES onboarding_runs(id) ON DELETE SET NULL,
            step_id UUID REFERENCES onboarding_steps(id) ON DELETE SET NULL,
            actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            provider VARCHAR(50) NOT NULL
                CHECK (provider IN ('google_workspace', 'slack')),
            action VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL
                CHECK (status IN ('success', 'error', 'info')),
            error_code VARCHAR(80),
            detail TEXT,
            payload JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provisioning_audit_logs_company_created
        ON provisioning_audit_logs(company_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provisioning_audit_logs_run
        ON provisioning_audit_logs(run_id)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_provisioning_audit_logs_run")
    op.execute("DROP INDEX IF EXISTS idx_provisioning_audit_logs_company_created")
    op.execute("DROP TABLE IF EXISTS provisioning_audit_logs")

    op.execute("DROP INDEX IF EXISTS idx_external_identities_company_provider")
    op.execute("DROP TABLE IF EXISTS external_identities")

    op.execute("DROP INDEX IF EXISTS idx_onboarding_steps_run_status")
    op.execute("DROP TABLE IF EXISTS onboarding_steps")

    op.execute("DROP INDEX IF EXISTS idx_onboarding_runs_employee_provider")
    op.execute("DROP INDEX IF EXISTS idx_onboarding_runs_company_provider_status")
    op.execute("DROP TABLE IF EXISTS onboarding_runs")

    op.execute("DROP INDEX IF EXISTS idx_integration_connections_status")
    op.execute("DROP INDEX IF EXISTS idx_integration_connections_company_provider")
    op.execute("DROP TABLE IF EXISTS integration_connections")
