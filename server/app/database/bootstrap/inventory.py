"""bootstrap.inventory — inventory_items + inventory_movements +
inventory_orders (mirrors alembic/versions/inventory01_channel_inventory.py).

Reference-only for a fresh DB bootstrap; schema changes always go through
Alembic (see server/CLAUDE.md's migration-authoring rules).
"""


async def create_inventory(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            unit VARCHAR(50),
            current_quantity NUMERIC,
            low_stock_threshold NUMERIC,
            auto_created BOOLEAN NOT NULL DEFAULT FALSE,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            archived_at TIMESTAMPTZ,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # Store scope for per-location catalogs (matches Alembic migration
    # oploc01). Guard kept separate from the CREATE TABLE above so an
    # existing pre-oploc01 table also picks up the column.
    await conn.execute("""
        ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS location_id UUID
        REFERENCES business_locations(id) ON DELETE SET NULL
    """)
    # NULLS NOT DISTINCT makes (company, NULL, name) collide exactly like
    # the pre-oploc01 (company, name) index — a company-wide item still has
    # one row, a store item is scoped to its own location_id.
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_items_name
        ON inventory_items (company_id, location_id, normalized_name)
        NULLS NOT DISTINCT WHERE archived_at IS NULL
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_mappings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            sold_name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('direct','recipe','ignore')),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_mappings_name
        ON inventory_sales_mappings (company_id, location_id, normalized_name)
        NULLS NOT DISTINCT
    """)
    await conn.execute("""
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
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_imports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            source VARCHAR(20) NOT NULL CHECK (source IN ('upload','email')),
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','committed','discarded')),
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
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_imports_gmail
        ON inventory_sales_imports (company_id, gmail_message_id)
        WHERE gmail_message_id IS NOT NULL
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_imports_period
        ON inventory_sales_imports (company_id, location_id, business_date)
        NULLS NOT DISTINCT WHERE status = 'committed' AND business_date IS NOT NULL
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            import_id UUID NOT NULL REFERENCES inventory_sales_imports(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            sold_name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            quantity NUMERIC NOT NULL,
            gross_sales NUMERIC,
            mapping_id UUID REFERENCES inventory_sales_mappings(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL CHECK (status IN ('mapped','unmapped','ignored')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
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

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('out','in','stockout','adjust','sale')),
            quantity NUMERIC,
            quantity_delta NUMERIC,
            quantity_estimated BOOLEAN NOT NULL DEFAULT FALSE,
            note TEXT,
            narrative TEXT NOT NULL,
            clarify_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            clarify_rounds SMALLINT NOT NULL DEFAULT 0,
            amended_by UUID REFERENCES users(id) ON DELETE SET NULL,
            amended_at TIMESTAMPTZ,
            sales_import_id UUID REFERENCES inventory_sales_imports(id) ON DELETE SET NULL,
            audit_run_id UUID REFERENCES inventory_audit_runs(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_kind_check")
    await conn.execute("""
        ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_kind_check
        CHECK (kind IN ('out','in','stockout','adjust','sale'))
    """)
    await conn.execute("""
        ALTER TABLE inventory_movements
        ADD COLUMN IF NOT EXISTS sales_import_id UUID
            REFERENCES inventory_sales_imports(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS audit_run_id UUID
            REFERENCES inventory_audit_runs(id) ON DELETE SET NULL
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_movements_message
        ON inventory_movements (source_message_id, item_id) WHERE source_message_id IS NOT NULL
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_movements_clarify
        ON inventory_movements (clarify_message_id) WHERE clarify_message_id IS NOT NULL
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_company
        ON inventory_movements (company_id, created_at DESC)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_item
        ON inventory_movements (item_id, created_at DESC)
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_movements_sales
        ON inventory_movements (sales_import_id, item_id)
        WHERE sales_import_id IS NOT NULL
    """)
    await conn.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS unit_cost NUMERIC")

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','ordered','received','cancelled')),
            suggested_quantity NUMERIC,
            quantity NUMERIC,
            suggestion JSONB,
            confirm_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ,
            ordered_at TIMESTAMPTZ,
            received_by UUID REFERENCES users(id) ON DELETE SET NULL,
            received_at TIMESTAMPTZ,
            received_quantity NUMERIC,
            receipt_movement_id UUID REFERENCES inventory_movements(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_orders_confirm
        ON inventory_orders (confirm_message_id) WHERE confirm_message_id IS NOT NULL
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_orders_open
        ON inventory_orders (item_id) WHERE status = 'queued'
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_orders_company
        ON inventory_orders (company_id, status, created_at DESC)
    """)
    await conn.execute("""
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
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_sources_address
        ON inventory_sales_sources (LOWER(from_address))
    """)
