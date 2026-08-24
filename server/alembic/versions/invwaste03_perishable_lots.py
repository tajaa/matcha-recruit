"""Advisory FEFO inventory lots for perishable stock."""

from alembic import op


revision = "invwaste03"
down_revision = "invwaste02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_lots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            received_movement_id UUID REFERENCES inventory_movements(id) ON DELETE SET NULL,
            lot_code VARCHAR(80),
            received_on DATE NOT NULL,
            expires_on DATE,
            quantity_received NUMERIC NOT NULL CHECK (quantity_received > 0),
            quantity_remaining NUMERIC NOT NULL CHECK (quantity_remaining >= 0),
            status VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (status IN ('open','depleted','discarded','expired')),
            unit_cost NUMERIC,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_lots_expiry
        ON inventory_lots (company_id, expires_on)
        WHERE status='open' AND expires_on IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_lots_receipt
        ON inventory_lots (received_movement_id, item_id)
        WHERE received_movement_id IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS uniq_inventory_lots_receipt")
    op.execute("DROP INDEX IF EXISTS idx_inventory_lots_expiry")
    op.execute("DROP TABLE IF EXISTS inventory_lots")
