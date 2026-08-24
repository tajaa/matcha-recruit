"""bootstrap.inventory — inventory_items + inventory_movements +
inventory_orders (mirrors alembic/versions/inventory01_channel_inventory.py).

Reference-only for a fresh DB bootstrap; schema changes always go through
Alembic (see server/CLAUDE.md's migration-authoring rules).
"""


async def create_inventory(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_pos_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            provider VARCHAR(30) NOT NULL CHECK (provider IN ('square','toast')),
            status VARCHAR(30) NOT NULL DEFAULT 'disconnected'
                CHECK (status IN ('connected','error','disconnected')),
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
            source VARCHAR(20) NOT NULL CHECK (source IN ('upload','email','square','toast')),
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','committed','discarded')),
            business_date DATE,
            filename VARCHAR(255),
            gmail_message_id VARCHAR(120),
            connection_id UUID REFERENCES inventory_pos_connections(id) ON DELETE SET NULL,
            external_batch_id VARCHAR(240),
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
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('out','in','stockout','adjust','sale','waste')),
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
        CHECK (kind IN ('out','in','stockout','adjust','sale','waste'))
    """)
    await conn.execute("ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS waste_reason VARCHAR(30)")
    await conn.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_waste_reason_check")
    await conn.execute("""
        ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_waste_reason_check
        CHECK (waste_reason IS NULL OR (kind='waste' AND waste_reason IN (
            'spoilage','expired','prep_error','overproduction',
            'breakage','contamination','theft','comp','recall','unknown')))
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_waste
        ON inventory_movements (company_id, created_at DESC) WHERE kind='waste'
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
    await conn.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS category VARCHAR(60)")
    await conn.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS shelf_life_days INT")
    await conn.execute("ALTER TABLE inventory_items DROP CONSTRAINT IF EXISTS inventory_items_shelf_life_days_check")
    await conn.execute("""
        ALTER TABLE inventory_items ADD CONSTRAINT inventory_items_shelf_life_days_check
        CHECK (shelf_life_days IS NULL OR shelf_life_days BETWEEN 1 AND 3650)
    """)
    await conn.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS yield_pct NUMERIC")
    await conn.execute("ALTER TABLE inventory_items DROP CONSTRAINT IF EXISTS inventory_items_yield_pct_check")
    await conn.execute("""
        ALTER TABLE inventory_items ADD CONSTRAINT inventory_items_yield_pct_check
        CHECK (yield_pct IS NULL OR (yield_pct > 0 AND yield_pct <= 1))
    """)

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
    await conn.execute("""
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
    await conn.execute("""
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
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_pos_sync_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            connection_id UUID NOT NULL REFERENCES inventory_pos_connections(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','completed','failed')),
            days_seen INT NOT NULL DEFAULT 0,
            imports_created INT NOT NULL DEFAULT 0,
            drafts_created INT NOT NULL DEFAULT 0,
            unmapped_lines INT NOT NULL DEFAULT 0,
            error TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_sales_imports_external_batch
        ON inventory_sales_imports (company_id, connection_id, external_batch_id)
        WHERE connection_id IS NOT NULL AND external_batch_id IS NOT NULL
    """)
    await conn.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('pos_sales_sync', 'POS API sales sync',
                'Sync finalized sales from connected POS providers', FALSE, 25)
        ON CONFLICT (task_key) DO NOTHING
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            horizon_days INT NOT NULL DEFAULT 56 CHECK (horizon_days BETWEEN 14 AND 90),
            history_days INT NOT NULL DEFAULT 90 CHECK (history_days BETWEEN 28 AND 365),
            default_lead_time_days INT NOT NULL DEFAULT 7 CHECK (default_lead_time_days BETWEEN 0 AND 180),
            default_safety_stock_days INT NOT NULL DEFAULT 7 CHECK (default_safety_stock_days BETWEEN 0 AND 180),
            timezone VARCHAR(80) NOT NULL DEFAULT 'America/Los_Angeles',
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_forecast_settings_scope
        ON inventory_forecast_settings (company_id, location_id) NULLS NOT DISTINCT
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_replenishment_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            lead_time_days INT NOT NULL CHECK (lead_time_days BETWEEN 0 AND 180),
            safety_stock_days INT NOT NULL CHECK (safety_stock_days BETWEEN 0 AND 180),
            case_pack_quantity NUMERIC NOT NULL CHECK (case_pack_quantity > 0),
            minimum_order_quantity NUMERIC NOT NULL DEFAULT 0 CHECK (minimum_order_quantity >= 0),
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, item_id)
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            forecast_start DATE NOT NULL,
            forecast_end DATE NOT NULL,
            history_start DATE NOT NULL,
            settings_snapshot JSONB NOT NULL,
            override_count INT NOT NULL DEFAULT 0,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_forecast_runs_scope
        ON inventory_forecast_runs (company_id, location_id, created_at DESC)
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_overrides (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            run_id UUID NOT NULL REFERENCES inventory_forecast_runs(id) ON DELETE CASCADE,
            week_start DATE NOT NULL,
            demand_multiplier NUMERIC NOT NULL CHECK (demand_multiplier BETWEEN 0.5 AND 2.0),
            reason VARCHAR(500) NOT NULL,
            source VARCHAR(20) NOT NULL CHECK (source IN ('manual', 'ai_accepted')),
            confidence VARCHAR(20),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_forecast_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES inventory_forecast_runs(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            status VARCHAR(30) NOT NULL CHECK (status IN ('ready', 'count_required', 'no_demand', 'insufficient_history')),
            confidence VARCHAR(20) NOT NULL,
            history_nonzero_days INT NOT NULL DEFAULT 0,
            current_quantity NUMERIC,
            on_order_quantity NUMERIC NOT NULL DEFAULT 0,
            projected_demand NUMERIC NOT NULL DEFAULT 0,
            average_daily_demand NUMERIC NOT NULL DEFAULT 0,
            lead_demand NUMERIC NOT NULL DEFAULT 0,
            safety_demand NUMERIC NOT NULL DEFAULT 0,
            target_quantity NUMERIC NOT NULL DEFAULT 0,
            suggested_quantity NUMERIC,
            runout_date DATE,
            order_by_date DATE,
            daily_demand JSONB NOT NULL DEFAULT '[]',
            calculation JSONB NOT NULL DEFAULT '{}',
            UNIQUE (run_id, item_id)
        )
    """)
