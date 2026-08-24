"""Inventory waste: new 'waste' movement kind + reason codes, and
perishability/category dimensions on inventory_items (shrinkage feature
phase 1 — see server/app/matcha/services/inventory/CLAUDE.md)."""

from alembic import op


revision = "invwaste01"
down_revision = "pos01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_kind_check")
    op.execute("""
        ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_kind_check
        CHECK (kind IN ('out', 'in', 'stockout', 'adjust', 'sale', 'waste'))
    """)
    op.execute("ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS waste_reason VARCHAR(30)")
    op.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_waste_reason_check")
    op.execute("""
        ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_waste_reason_check
        CHECK (waste_reason IS NULL OR (kind = 'waste' AND waste_reason IN (
            'spoilage', 'expired', 'prep_error', 'overproduction',
            'breakage', 'contamination', 'theft', 'comp', 'recall', 'unknown'
        )))
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_waste
        ON inventory_movements (company_id, created_at DESC)
        WHERE kind = 'waste'
    """)

    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS category VARCHAR(60)")

    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS shelf_life_days INT")
    op.execute("ALTER TABLE inventory_items DROP CONSTRAINT IF EXISTS inventory_items_shelf_life_days_check")
    op.execute("""
        ALTER TABLE inventory_items ADD CONSTRAINT inventory_items_shelf_life_days_check
        CHECK (shelf_life_days IS NULL OR shelf_life_days BETWEEN 1 AND 3650)
    """)

    op.execute("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS yield_pct NUMERIC")
    op.execute("ALTER TABLE inventory_items DROP CONSTRAINT IF EXISTS inventory_items_yield_pct_check")
    op.execute("""
        ALTER TABLE inventory_items ADD CONSTRAINT inventory_items_yield_pct_check
        CHECK (yield_pct IS NULL OR (yield_pct > 0 AND yield_pct <= 1))
    """)

    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'inventory_expiry_sweep', 'Inventory expiry sweep',
            'Nudge stores in-channel about lots expiring soon',
            FALSE, 200
        )
        ON CONFLICT (task_key) DO NOTHING
    """)
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'inventory_waste_digest', 'Inventory waste digest',
            'Weekly waste percent-of-revenue and top-bleeder summary per location',
            FALSE, 200
        )
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'inventory_waste_digest'")
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'inventory_expiry_sweep'")

    op.execute("ALTER TABLE inventory_items DROP CONSTRAINT IF EXISTS inventory_items_yield_pct_check")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS yield_pct")
    op.execute("ALTER TABLE inventory_items DROP CONSTRAINT IF EXISTS inventory_items_shelf_life_days_check")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS shelf_life_days")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS category")

    op.execute("DROP INDEX IF EXISTS idx_inventory_movements_waste")
    op.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_waste_reason_check")
    op.execute("ALTER TABLE inventory_movements DROP COLUMN IF EXISTS waste_reason")
    # A downgrade with existing 'waste' rows would violate the narrower
    # CHECK below — same tradeoff sales01's downgrade makes for 'sale'.
    op.execute("ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS inventory_movements_kind_check")
    op.execute("""
        ALTER TABLE inventory_movements ADD CONSTRAINT inventory_movements_kind_check
        CHECK (kind IN ('out', 'in', 'stockout', 'adjust', 'sale'))
    """)
