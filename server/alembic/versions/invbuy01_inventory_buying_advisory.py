"""Inventory buying advisory supplier evidence and immutable plan snapshots."""

from alembic import op


revision = "invbuy01"
down_revision = "sales02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE inventory_suppliers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            contact_email VARCHAR(320), contact_phone VARCHAR(80),
            payment_terms VARCHAR(120), active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, normalized_name)
        )
    """)
    op.execute("""
        CREATE TABLE inventory_supplier_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            supplier_id UUID NOT NULL REFERENCES inventory_suppliers(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE CASCADE,
            vendor_sku VARCHAR(80), purchase_unit VARCHAR(50), pack_size_label VARCHAR(80),
            units_per_pack NUMERIC NOT NULL DEFAULT 1 CHECK (units_per_pack > 0),
            minimum_order_quantity NUMERIC NOT NULL DEFAULT 0 CHECK (minimum_order_quantity >= 0),
            unit_price NUMERIC CHECK (unit_price IS NULL OR unit_price >= 0),
            freight_flat NUMERIC CHECK (freight_flat IS NULL OR freight_flat >= 0),
            lead_time_days INT CHECK (lead_time_days IS NULL OR lead_time_days BETWEEN 0 AND 180),
            price_observed_on DATE, preferred BOOLEAN NOT NULL DEFAULT FALSE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE UNIQUE INDEX uniq_inventory_supplier_item_scope
        ON inventory_supplier_items (supplier_id, item_id, location_id) NULLS NOT DISTINCT""")
    op.execute("""CREATE INDEX idx_inventory_supplier_items_company
        ON inventory_supplier_items (company_id, item_id, location_id)""")
    op.execute("""
        CREATE TABLE inventory_supplier_price_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            supplier_item_id UUID NOT NULL REFERENCES inventory_supplier_items(id) ON DELETE CASCADE,
            unit_price NUMERIC NOT NULL CHECK (unit_price >= 0),
            quantity NUMERIC CHECK (quantity IS NULL OR quantity > 0),
            freight NUMERIC CHECK (freight IS NULL OR freight >= 0),
            observed_on DATE NOT NULL, invoice_number VARCHAR(80),
            source VARCHAR(20) NOT NULL CHECK (source IN ('receipt','manual')),
            reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX idx_inventory_supplier_prices
        ON inventory_supplier_price_history (supplier_item_id, observed_on DESC, created_at DESC)""")
    op.execute("""
        CREATE TABLE inventory_buying_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            forecast_run_id UUID NOT NULL REFERENCES inventory_forecast_runs(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            input_fingerprint VARCHAR(64) NOT NULL,
            summary JSONB NOT NULL DEFAULT '{}',
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX idx_inventory_buying_runs_scope
        ON inventory_buying_runs (company_id, location_id, created_at DESC)""")
    op.execute("""
        CREATE TABLE inventory_buying_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES inventory_buying_runs(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            action VARCHAR(24) NOT NULL CHECK (action IN ('count_first','hold','buy','expedite')),
            needed_quantity NUMERIC, purchase_quantity NUMERIC,
            supplier_id UUID REFERENCES inventory_suppliers(id) ON DELETE SET NULL,
            supplier_item_id UUID REFERENCES inventory_supplier_items(id) ON DELETE SET NULL,
            order_by_date DATE, expected_arrival DATE, landed_cost NUMERIC,
            confidence VARCHAR(20) NOT NULL,
            price_confirmation_required BOOLEAN NOT NULL DEFAULT FALSE,
            rationale TEXT NOT NULL, alternatives JSONB NOT NULL DEFAULT '[]',
            calculation JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX idx_inventory_buying_lines_run ON inventory_buying_lines (run_id)""")
    op.execute("ALTER TABLE inventory_orders ADD COLUMN supplier_id UUID REFERENCES inventory_suppliers(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE inventory_orders ADD COLUMN supplier_item_id UUID REFERENCES inventory_supplier_items(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE inventory_orders ADD COLUMN expected_delivery DATE")
    op.execute("ALTER TABLE inventory_orders ADD COLUMN unit_price_snapshot NUMERIC")
    op.execute("ALTER TABLE inventory_orders ADD COLUMN freight_snapshot NUMERIC")
    op.execute("ALTER TABLE inventory_orders ADD COLUMN buying_line_id UUID REFERENCES inventory_buying_lines(id) ON DELETE SET NULL")


def downgrade():
    op.execute("ALTER TABLE inventory_orders DROP COLUMN IF EXISTS buying_line_id")
    op.execute("ALTER TABLE inventory_orders DROP COLUMN IF EXISTS freight_snapshot")
    op.execute("ALTER TABLE inventory_orders DROP COLUMN IF EXISTS unit_price_snapshot")
    op.execute("ALTER TABLE inventory_orders DROP COLUMN IF EXISTS expected_delivery")
    op.execute("ALTER TABLE inventory_orders DROP COLUMN IF EXISTS supplier_item_id")
    op.execute("ALTER TABLE inventory_orders DROP COLUMN IF EXISTS supplier_id")
    op.execute("DROP TABLE inventory_buying_lines")
    op.execute("DROP TABLE inventory_buying_runs")
    op.execute("DROP TABLE inventory_supplier_price_history")
    op.execute("DROP TABLE inventory_supplier_items")
    op.execute("DROP TABLE inventory_suppliers")
