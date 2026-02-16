"""add broker channel foundation

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-02-16
"""

from alembic import op


revision = "u1v2w3x4y5z6"
down_revision = "t0u1v2w3x4y5"
branch_labels = None
depends_on = None


def upgrade():
    # Extend users role constraint with broker role.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check') THEN
                ALTER TABLE users DROP CONSTRAINT users_role_check;
            END IF;

            ALTER TABLE users ADD CONSTRAINT users_role_check
                CHECK (role IN ('admin', 'client', 'candidate', 'employee', 'broker', 'creator', 'agency', 'gumfit_admin'));
        EXCEPTION WHEN others THEN
            NULL;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS brokers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(120) NOT NULL UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('pending', 'active', 'suspended', 'terminated')),
            support_routing VARCHAR(20) NOT NULL DEFAULT 'shared'
                CHECK (support_routing IN ('broker_first', 'matcha_first', 'shared')),
            billing_mode VARCHAR(20) NOT NULL DEFAULT 'direct'
                CHECK (billing_mode IN ('direct', 'reseller', 'hybrid')),
            invoice_owner VARCHAR(20) NOT NULL DEFAULT 'matcha'
                CHECK (invoice_owner IN ('matcha', 'broker')),
            terms_required_version VARCHAR(50) NOT NULL DEFAULT 'v1',
            created_by UUID REFERENCES users(id),
            terminated_at TIMESTAMPTZ,
            grace_until TIMESTAMPTZ,
            post_termination_mode VARCHAR(30)
                CHECK (post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset')),
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_brokers_status ON brokers(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_brokers_created_at ON brokers(created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL DEFAULT 'member'
                CHECK (role IN ('owner', 'admin', 'member')),
            permissions JSONB DEFAULT '{}'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (broker_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_members_user_id ON broker_members(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_members_broker_id ON broker_members(broker_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_company_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'active', 'suspending', 'grace', 'terminated', 'transferred')),
            permissions JSONB DEFAULT '{}'::jsonb,
            linked_at TIMESTAMPTZ DEFAULT NOW(),
            activated_at TIMESTAMPTZ,
            terminated_at TIMESTAMPTZ,
            grace_until TIMESTAMPTZ,
            post_termination_mode VARCHAR(30)
                CHECK (post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset')),
            created_by UUID REFERENCES users(id),
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (broker_id, company_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_company_links_company_id ON broker_company_links(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_company_links_status ON broker_company_links(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_company_links_broker_status ON broker_company_links(broker_id, status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_contracts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'suspended', 'terminated')),
            billing_mode VARCHAR(20) NOT NULL
                CHECK (billing_mode IN ('direct', 'reseller', 'hybrid')),
            invoice_owner VARCHAR(20) NOT NULL
                CHECK (invoice_owner IN ('matcha', 'broker')),
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            base_platform_fee NUMERIC(12, 2) NOT NULL DEFAULT 0,
            pepm_rate NUMERIC(12, 2) NOT NULL DEFAULT 0,
            minimum_monthly_commit NUMERIC(12, 2) NOT NULL DEFAULT 0,
            pricing_rules JSONB DEFAULT '{}'::jsonb,
            effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ,
            created_by UUID REFERENCES users(id),
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_contracts_broker_id ON broker_contracts(broker_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_contracts_status ON broker_contracts(status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_terms_acceptances (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            terms_version VARCHAR(50) NOT NULL,
            accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_address VARCHAR(64),
            user_agent TEXT,
            UNIQUE (broker_id, user_id, terms_version)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_terms_acceptances_lookup
        ON broker_terms_acceptances(broker_id, user_id, terms_version)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_broker_terms_acceptances_lookup")
    op.execute("DROP TABLE IF EXISTS broker_terms_acceptances")

    op.execute("DROP INDEX IF EXISTS idx_broker_contracts_status")
    op.execute("DROP INDEX IF EXISTS idx_broker_contracts_broker_id")
    op.execute("DROP TABLE IF EXISTS broker_contracts")

    op.execute("DROP INDEX IF EXISTS idx_broker_company_links_broker_status")
    op.execute("DROP INDEX IF EXISTS idx_broker_company_links_status")
    op.execute("DROP INDEX IF EXISTS idx_broker_company_links_company_id")
    op.execute("DROP TABLE IF EXISTS broker_company_links")

    op.execute("DROP INDEX IF EXISTS idx_broker_members_broker_id")
    op.execute("DROP INDEX IF EXISTS idx_broker_members_user_id")
    op.execute("DROP TABLE IF EXISTS broker_members")

    op.execute("DROP INDEX IF EXISTS idx_brokers_created_at")
    op.execute("DROP INDEX IF EXISTS idx_brokers_status")
    op.execute("DROP TABLE IF EXISTS brokers")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check') THEN
                ALTER TABLE users DROP CONSTRAINT users_role_check;
            END IF;

            ALTER TABLE users ADD CONSTRAINT users_role_check
                CHECK (role IN ('admin', 'client', 'candidate', 'employee', 'creator', 'agency', 'gumfit_admin'));
        EXCEPTION WHEN others THEN
            NULL;
        END $$;
        """
    )
