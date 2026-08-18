"""inventory: POS sales intake and durable audit variance reports.

Sales imports are intentionally separate from chat movements.  The unique
period key prevents a nightly export from being applied twice, while the
sales-import movement key makes a retried commit idempotent at the ledger
level as well.
"""

from alembic import op


revision = "sales01"
down_revision = "huumeasset01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_mappings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            sold_name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('direct', 'recipe', 'ignore')),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_mappings_name
        ON inventory_sales_mappings (company_id, location_id, normalized_name)
        NULLS NOT DISTINCT
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_mapping_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            mapping_id UUID NOT NULL REFERENCES inventory_sales_mappings(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            quantity_per_sale NUMERIC NOT NULL CHECK (quantity_per_sale > 0),
            unit VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (mapping_id, item_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_imports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            source VARCHAR(20) NOT NULL CHECK (source IN ('upload', 'email')),
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'committed', 'discarded')),
            business_date DATE,
            filename VARCHAR(255),
            gmail_message_id VARCHAR(120),
            raw JSONB,
            uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            committed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            committed_at TIMESTAMPTZ,
            line_count INT NOT NULL DEFAULT 0,
            mapped_count INT NOT NULL DEFAULT 0,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_imports_gmail
        ON inventory_sales_imports (company_id, gmail_message_id)
        WHERE gmail_message_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_imports_period
        ON inventory_sales_imports (company_id, location_id, business_date)
        NULLS NOT DISTINCT
        WHERE status = 'committed' AND business_date IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            import_id UUID NOT NULL REFERENCES inventory_sales_imports(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            sold_name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            quantity NUMERIC NOT NULL,
            gross_sales NUMERIC,
            mapping_id UUID REFERENCES inventory_sales_mappings(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL CHECK (status IN ('mapped', 'unmapped', 'ignored')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_audit_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            committed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            note TEXT,
            line_count INT NOT NULL DEFAULT 0,
            variance_units NUMERIC,
            variance_value NUMERIC
        )
    """)
    op.execute("""
        ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_kind_check
    """)
    op.execute("""
        ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_kind_check
        CHECK (kind IN ('out', 'in', 'stockout', 'adjust', 'sale'))
    """)
    op.execute("""
        ALTER TABLE inventory_movements
        ADD COLUMN IF NOT EXISTS sales_import_id UUID
            REFERENCES inventory_sales_imports(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS audit_run_id UUID
            REFERENCES inventory_audit_runs(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_movements_sales
        ON inventory_movements (sales_import_id, item_id)
        WHERE sales_import_id IS NOT NULL
    """)
    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS unit_cost NUMERIC")
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_sources (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            from_address VARCHAR(320) NOT NULL,
            subject_match VARCHAR(200),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_sources_address
        ON inventory_sales_sources (LOWER(from_address))
    """)
    op.execute("""
        INSERT INTO scheduler_settings
            (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'sales_intake_poll', 'POS sales intake',
            'Poll the dedicated Gmail inbox for scheduled POS sales exports',
            FALSE, 25
        )
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key='sales_intake_poll'")
    op.execute("DROP TABLE IF EXISTS inventory_sales_sources")
    op.execute("DROP INDEX IF EXISTS uniq_inventory_movements_sales")
    op.execute("ALTER TABLE inventory_movements DROP COLUMN IF EXISTS audit_run_id")
    op.execute("ALTER TABLE inventory_movements DROP COLUMN IF EXISTS sales_import_id")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS unit_cost")
    op.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_kind_check")
    op.execute("""
        ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_kind_check
        CHECK (kind IN ('out', 'in', 'stockout', 'adjust'))
    """)
    op.execute("DROP TABLE IF EXISTS inventory_audit_runs")
    op.execute("DROP TABLE IF EXISTS inventory_sales_lines")
    op.execute("DROP INDEX IF EXISTS uniq_inventory_sales_imports_period")
    op.execute("DROP INDEX IF EXISTS uniq_inventory_sales_imports_gmail")
    op.execute("DROP TABLE IF EXISTS inventory_sales_imports")
    op.execute("DROP TABLE IF EXISTS inventory_sales_mapping_lines")
    op.execute("DROP INDEX IF EXISTS uniq_inventory_sales_mappings_name")
    op.execute("DROP TABLE IF EXISTS inventory_sales_mappings")
