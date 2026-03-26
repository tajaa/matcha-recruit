"""add credential_requirement_templates, credential_research_logs, employee_credential_requirements

Revision ID: z1a2b3c4d5e6
Revises: y0z1a2b3c4d5
Create Date: 2026-03-26
"""

from alembic import op


revision = "z1a2b3c4d5e6"
down_revision = "y0z1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── credential_research_logs: AI audit trail ──────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS credential_research_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
            state VARCHAR(2) NOT NULL,
            city VARCHAR(100),
            role_category_id UUID REFERENCES role_categories(id),
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            template_count INT DEFAULT 0,
            ai_model VARCHAR(60),
            error_message TEXT,
            triggered_by UUID REFERENCES users(id),
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_crl_company
            ON credential_research_logs(company_id, started_at DESC)
    """)

    # ── credential_requirement_templates: core template table ─────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS credential_requirement_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
            state VARCHAR(2) NOT NULL,
            city VARCHAR(100),
            role_category_id UUID NOT NULL REFERENCES role_categories(id),
            credential_type_id UUID NOT NULL REFERENCES credential_types(id),
            is_required BOOLEAN NOT NULL DEFAULT true,
            due_days INT NOT NULL DEFAULT 7,
            priority VARCHAR(20) NOT NULL DEFAULT 'standard',
            notes TEXT,
            source VARCHAR(30) NOT NULL DEFAULT 'ai_research',
            ai_research_id UUID REFERENCES credential_research_logs(id),
            ai_confidence DECIMAL(3,2),
            review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            reviewed_by UUID REFERENCES users(id),
            reviewed_at TIMESTAMP,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE NULLS NOT DISTINCT (company_id, state, city, role_category_id, credential_type_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_crt_company
            ON credential_requirement_templates(company_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_crt_lookup
            ON credential_requirement_templates(company_id, state, role_category_id)
            WHERE is_active = true AND review_status IN ('approved', 'auto_approved')
    """)

    # ── employee_credential_requirements: per-employee materialized ───
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_credential_requirements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            credential_type_id UUID NOT NULL REFERENCES credential_types(id),
            template_id UUID REFERENCES credential_requirement_templates(id),
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            is_required BOOLEAN NOT NULL DEFAULT true,
            priority VARCHAR(20) NOT NULL DEFAULT 'standard',
            due_date DATE,
            onboarding_task_id UUID,
            credential_document_id UUID REFERENCES credential_documents(id),
            verified_at TIMESTAMP,
            verified_by UUID REFERENCES users(id),
            waived_at TIMESTAMP,
            waived_by UUID REFERENCES users(id),
            waiver_reason TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(employee_id, credential_type_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ecr_employee
            ON employee_credential_requirements(employee_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ecr_pending
            ON employee_credential_requirements(status)
            WHERE status = 'pending'
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS employee_credential_requirements")
    op.execute("DROP TABLE IF EXISTS credential_requirement_templates")
    op.execute("DROP TABLE IF EXISTS credential_research_logs")
