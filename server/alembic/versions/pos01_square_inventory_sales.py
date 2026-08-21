"""Square POS connections and normalized sales-sync provenance."""

from alembic import op


revision = "pos01"
down_revision = "invforecast01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_pos_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            provider VARCHAR(30) NOT NULL CHECK (provider IN ('square', 'toast')),
            status VARCHAR(30) NOT NULL DEFAULT 'disconnected'
                CHECK (status IN ('connected', 'error', 'disconnected')),
            config JSONB NOT NULL DEFAULT '{}',
            secrets JSONB NOT NULL DEFAULT '{}',
            last_sync_at TIMESTAMPTZ,
            last_error TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, provider)
        )
    """)
    op.execute("""
        ALTER TABLE inventory_sales_imports DROP CONSTRAINT IF EXISTS inventory_sales_imports_source_check
    """)
    op.execute("""
        ALTER TABLE inventory_sales_imports ADD CONSTRAINT inventory_sales_imports_source_check
        CHECK (source IN ('upload', 'email', 'square', 'toast'))
    """)
    op.execute("""
        ALTER TABLE inventory_sales_imports
            ADD COLUMN IF NOT EXISTS connection_id UUID
                REFERENCES inventory_pos_connections(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS external_batch_id VARCHAR(240)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_pos_location_bindings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            connection_id UUID NOT NULL REFERENCES inventory_pos_connections(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            external_location_id VARCHAR(120) NOT NULL,
            name VARCHAR(200) NOT NULL,
            timezone VARCHAR(80) NOT NULL DEFAULT 'UTC',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (connection_id, external_location_id),
            UNIQUE (connection_id, location_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_pos_mapping_keys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            connection_id UUID NOT NULL REFERENCES inventory_pos_connections(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            external_item_id VARCHAR(200) NOT NULL,
            mapping_id UUID NOT NULL REFERENCES inventory_sales_mappings(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (connection_id, external_item_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_pos_sync_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            connection_id UUID NOT NULL REFERENCES inventory_pos_connections(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'completed', 'failed')),
            days_seen INT NOT NULL DEFAULT 0,
            imports_created INT NOT NULL DEFAULT 0,
            drafts_created INT NOT NULL DEFAULT 0,
            unmapped_lines INT NOT NULL DEFAULT 0,
            error TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_imports_external_batch
        ON inventory_sales_imports (company_id, connection_id, external_batch_id)
        WHERE connection_id IS NOT NULL AND external_batch_id IS NOT NULL
    """)
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('pos_sales_sync', 'POS API sales sync',
                'Sync finalized sales from connected POS providers', FALSE, 25)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key='pos_sales_sync'")
    op.execute("DROP INDEX IF EXISTS uniq_inventory_sales_imports_external_batch")
    op.execute("DROP TABLE IF EXISTS inventory_pos_sync_runs")
    op.execute("DROP TABLE IF EXISTS inventory_pos_mapping_keys")
    op.execute("DROP TABLE IF EXISTS inventory_pos_location_bindings")
    op.execute("DROP TABLE IF EXISTS inventory_pos_connections")
    op.execute("ALTER TABLE inventory_sales_imports DROP COLUMN IF EXISTS connection_id")
    op.execute("ALTER TABLE inventory_sales_imports DROP COLUMN IF EXISTS external_batch_id")
    op.execute("ALTER TABLE inventory_sales_imports DROP CONSTRAINT IF EXISTS inventory_sales_imports_source_check")
    op.execute("""
        ALTER TABLE inventory_sales_imports ADD CONSTRAINT inventory_sales_imports_source_check
        CHECK (source IN ('upload', 'email'))
    """)
