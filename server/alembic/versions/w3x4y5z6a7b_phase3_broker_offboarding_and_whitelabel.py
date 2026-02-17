"""phase3 broker offboarding and whitelabel

Revision ID: w3x4y5z6a7b
Revises: v2w3x4y5z6a
Create Date: 2026-02-16
"""

from alembic import op


revision = "w3x4y5z6a7b"
down_revision = "v2w3x4y5z6a"
branch_labels = None
depends_on = None


def _replace_post_termination_constraint(table_name: str, values: list[str], constraint_name: str) -> None:
    values_sql = ", ".join(f"'{value}'" for value in values)
    values_sql_escaped = values_sql.replace("'", "''")
    op.execute(
        f"""
        DO $$
        DECLARE existing_constraint TEXT;
        BEGIN
            SELECT c.conname INTO existing_constraint
            FROM pg_constraint c
            WHERE c.conrelid = '{table_name}'::regclass
              AND c.contype = 'c'
              AND pg_get_constraintdef(c.oid) ILIKE '%post_termination_mode%';

            IF existing_constraint IS NOT NULL THEN
                EXECUTE format('ALTER TABLE {table_name} DROP CONSTRAINT %I', existing_constraint);
            END IF;

            EXECUTE 'ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} ' ||
                    'CHECK (post_termination_mode IS NULL OR post_termination_mode IN ({values_sql_escaped}))';
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END $$;
        """
    )


def upgrade():
    _replace_post_termination_constraint(
        table_name="brokers",
        values=["convert_to_direct", "transfer_to_broker", "sunset", "matcha_managed"],
        constraint_name="brokers_post_termination_mode_check",
    )
    _replace_post_termination_constraint(
        table_name="broker_company_links",
        values=["convert_to_direct", "transfer_to_broker", "sunset", "matcha_managed"],
        constraint_name="broker_company_links_post_termination_mode_check",
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_branding_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL UNIQUE REFERENCES brokers(id) ON DELETE CASCADE,
            branding_mode VARCHAR(20) NOT NULL DEFAULT 'direct'
                CHECK (branding_mode IN ('direct', 'co_branded', 'white_label')),
            brand_display_name VARCHAR(255),
            brand_legal_name VARCHAR(255),
            logo_url TEXT,
            favicon_url TEXT,
            primary_color VARCHAR(20),
            secondary_color VARCHAR(20),
            login_subdomain VARCHAR(120) UNIQUE,
            custom_login_url TEXT,
            support_email VARCHAR(320),
            support_phone VARCHAR(50),
            support_url TEXT,
            email_from_name VARCHAR(255),
            email_from_address VARCHAR(320),
            powered_by_badge BOOLEAN NOT NULL DEFAULT true,
            hide_matcha_identity BOOLEAN NOT NULL DEFAULT false,
            mobile_branding_enabled BOOLEAN NOT NULL DEFAULT false,
            theme JSONB DEFAULT '{}'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_by UUID REFERENCES users(id),
            updated_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_branding_mode
        ON broker_branding_configs(branding_mode)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_company_transitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            source_link_id UUID REFERENCES broker_company_links(id) ON DELETE SET NULL,
            mode VARCHAR(30) NOT NULL
                CHECK (mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed')),
            status VARCHAR(20) NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled')),
            transfer_target_broker_id UUID REFERENCES brokers(id),
            grace_until TIMESTAMPTZ,
            matcha_managed_until TIMESTAMPTZ,
            data_handoff_status VARCHAR(20) NOT NULL DEFAULT 'not_required'
                CHECK (data_handoff_status IN ('not_required', 'pending', 'in_progress', 'completed')),
            data_handoff_notes TEXT,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_by UUID REFERENCES users(id),
            updated_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_company_transitions_broker_company
        ON broker_company_transitions(broker_id, company_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_company_transitions_transfer_target
        ON broker_company_transitions(transfer_target_broker_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_broker_company_transitions_active_single
        ON broker_company_transitions(broker_id, company_id)
        WHERE status IN ('planned', 'in_progress')
        """
    )

    op.execute(
        """
        ALTER TABLE broker_company_links
        ADD COLUMN IF NOT EXISTS transition_state VARCHAR(20) DEFAULT 'none'
        """
    )
    op.execute(
        """
        ALTER TABLE broker_company_links
        ADD COLUMN IF NOT EXISTS transition_updated_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        ALTER TABLE broker_company_links
        ADD COLUMN IF NOT EXISTS data_handoff_status VARCHAR(20) DEFAULT 'not_required'
        """
    )
    op.execute(
        """
        ALTER TABLE broker_company_links
        ADD COLUMN IF NOT EXISTS data_handoff_notes TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE broker_company_links
        ADD COLUMN IF NOT EXISTS current_transition_id UUID
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'broker_company_links_transition_state_check'
            ) THEN
                ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_transition_state_check;
            END IF;

            ALTER TABLE broker_company_links
            ADD CONSTRAINT broker_company_links_transition_state_check
            CHECK (transition_state IN ('none', 'planned', 'in_progress', 'matcha_managed', 'completed'));
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'broker_company_links_data_handoff_status_check'
            ) THEN
                ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_data_handoff_status_check;
            END IF;

            ALTER TABLE broker_company_links
            ADD CONSTRAINT broker_company_links_data_handoff_status_check
            CHECK (data_handoff_status IN ('not_required', 'pending', 'in_progress', 'completed'));
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'broker_company_links_current_transition_id_fkey'
            ) THEN
                ALTER TABLE broker_company_links
                ADD CONSTRAINT broker_company_links_current_transition_id_fkey
                FOREIGN KEY (current_transition_id)
                REFERENCES broker_company_transitions(id)
                ON DELETE SET NULL;
            END IF;
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END $$;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_company_links_transition_state
        ON broker_company_links(transition_state)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_company_links_current_transition
        ON broker_company_links(current_transition_id)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_broker_company_links_current_transition")
    op.execute("DROP INDEX IF EXISTS idx_broker_company_links_transition_state")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'broker_company_links_current_transition_id_fkey'
            ) THEN
                ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_current_transition_id_fkey;
            END IF;
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'broker_company_links_data_handoff_status_check'
            ) THEN
                ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_data_handoff_status_check;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'broker_company_links_transition_state_check'
            ) THEN
                ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_transition_state_check;
            END IF;
        EXCEPTION WHEN undefined_table THEN
            NULL;
        END $$;
        """
    )

    op.execute("ALTER TABLE broker_company_links DROP COLUMN IF EXISTS current_transition_id")
    op.execute("ALTER TABLE broker_company_links DROP COLUMN IF EXISTS data_handoff_notes")
    op.execute("ALTER TABLE broker_company_links DROP COLUMN IF EXISTS data_handoff_status")
    op.execute("ALTER TABLE broker_company_links DROP COLUMN IF EXISTS transition_updated_at")
    op.execute("ALTER TABLE broker_company_links DROP COLUMN IF EXISTS transition_state")

    op.execute("DROP INDEX IF EXISTS idx_broker_company_transitions_active_single")
    op.execute("DROP INDEX IF EXISTS idx_broker_company_transitions_transfer_target")
    op.execute("DROP INDEX IF EXISTS idx_broker_company_transitions_broker_company")
    op.execute("DROP TABLE IF EXISTS broker_company_transitions")

    op.execute("DROP INDEX IF EXISTS idx_broker_branding_mode")
    op.execute("DROP TABLE IF EXISTS broker_branding_configs")

    _replace_post_termination_constraint(
        table_name="broker_company_links",
        values=["convert_to_direct", "transfer_to_broker", "sunset"],
        constraint_name="broker_company_links_post_termination_mode_check",
    )
    _replace_post_termination_constraint(
        table_name="brokers",
        values=["convert_to_direct", "transfer_to_broker", "sunset"],
        constraint_name="brokers_post_termination_mode_check",
    )
