"""Add fractional HR engagement tooling tables.

Internal master-admin vertical for delivering HR fractionally to clients:
engagements (clients), pro assignments, scope items, tasks, time entries,
and an audit log. No client-facing login — operated by Matcha admins.

Revision ID: zzzzfhr1a2b3
Revises: authsess01
Create Date: 2026-06-07
"""
from alembic import op


revision = "zzzzfhr1a2b3"
down_revision = "authsess01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Engagements. company_id is nullable — a fractional client may have no
    # platform tenant (no login yet); identity lives on the row itself.
    op.execute("""
        CREATE TABLE IF NOT EXISTS fractional_clients (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'prospect'
                CHECK (status IN ('prospect', 'active', 'paused', 'offboarded')),
            billing_model VARCHAR(20) NOT NULL DEFAULT 'monthly_retainer'
                CHECK (billing_model IN ('monthly_retainer', 'hours_block', 'project_fixed', 'hourly')),
            retainer_hours NUMERIC(8, 2),
            retainer_period VARCHAR(12) NOT NULL DEFAULT 'monthly'
                CHECK (retainer_period IN ('weekly', 'monthly', 'quarterly')),
            rollover_unused BOOLEAN NOT NULL DEFAULT false,
            billing_rate NUMERIC(10, 2),
            project_fee NUMERIC(12, 2),
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            industry VARCHAR(100),
            headcount INTEGER,
            jurisdictions JSONB NOT NULL DEFAULT '[]'::jsonb,
            contact_name VARCHAR(255),
            contact_email VARCHAR(320),
            contact_phone VARCHAR(50),
            lead_pro_id UUID REFERENCES users(id) ON DELETE SET NULL,
            start_date DATE,
            notes TEXT,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_clients_status ON fractional_clients(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_clients_company_id ON fractional_clients(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_clients_lead_pro ON fractional_clients(lead_pro_id)")

    # Pro assignments (team on an engagement — supports a jr HR team under a lead).
    op.execute("""
        CREATE TABLE IF NOT EXISTS fractional_assignments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES fractional_clients(id) ON DELETE CASCADE,
            pro_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL DEFAULT 'consultant'
                CHECK (role IN ('lead', 'consultant', 'jr')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (client_id, pro_user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_assignments_client ON fractional_assignments(client_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_assignments_pro ON fractional_assignments(pro_user_id)")

    # Scope items — what is in scope for this engagement.
    op.execute("""
        CREATE TABLE IF NOT EXISTS fractional_scope_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES fractional_clients(id) ON DELETE CASCADE,
            service_category VARCHAR(40) NOT NULL DEFAULT 'other',
            title VARCHAR(255) NOT NULL,
            description TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned', 'active', 'on_hold', 'done')),
            priority VARCHAR(10) NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high')),
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_scope_client ON fractional_scope_items(client_id, status)")

    # Tasks — actionable work items.
    op.execute("""
        CREATE TABLE IF NOT EXISTS fractional_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES fractional_clients(id) ON DELETE CASCADE,
            scope_item_id UUID REFERENCES fractional_scope_items(id) ON DELETE SET NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            service_category VARCHAR(40) NOT NULL DEFAULT 'other',
            status VARCHAR(20) NOT NULL DEFAULT 'todo'
                CHECK (status IN ('todo', 'in_progress', 'blocked', 'review', 'done')),
            priority VARCHAR(10) NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high')),
            assignee_pro_id UUID REFERENCES users(id) ON DELETE SET NULL,
            due_date DATE,
            estimated_hours NUMERIC(6, 2),
            billable BOOLEAN NOT NULL DEFAULT true,
            created_by UUID REFERENCES users(id),
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_tasks_client_status ON fractional_tasks(client_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_tasks_assignee ON fractional_tasks(assignee_pro_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_tasks_due ON fractional_tasks(due_date)")

    # Time entries — drive retainer burn / utilization.
    op.execute("""
        CREATE TABLE IF NOT EXISTS fractional_time_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES fractional_clients(id) ON DELETE CASCADE,
            task_id UUID REFERENCES fractional_tasks(id) ON DELETE SET NULL,
            pro_id UUID NOT NULL REFERENCES users(id),
            hours NUMERIC(6, 2) NOT NULL,
            entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
            note TEXT,
            billable BOOLEAN NOT NULL DEFAULT true,
            service_category VARCHAR(40),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_time_client_date ON fractional_time_entries(client_id, entry_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_time_task ON fractional_time_entries(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_time_pro ON fractional_time_entries(pro_id)")

    # Lightweight audit log (per-domain convention).
    op.execute("""
        CREATE TABLE IF NOT EXISTS fractional_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID REFERENCES fractional_clients(id) ON DELETE SET NULL,
            actor_id UUID REFERENCES users(id),
            action VARCHAR(64) NOT NULL,
            detail JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_fractional_audit_client ON fractional_audit_log(client_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fractional_audit_log")
    op.execute("DROP TABLE IF EXISTS fractional_time_entries")
    op.execute("DROP TABLE IF EXISTS fractional_tasks")
    op.execute("DROP TABLE IF EXISTS fractional_scope_items")
    op.execute("DROP TABLE IF EXISTS fractional_assignments")
    op.execute("DROP TABLE IF EXISTS fractional_clients")
