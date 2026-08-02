"""Inventory tracking via @huume channel intake — inventory_items,
inventory_movements (append-only ledger), inventory_orders.

Backs the `inventory` feature flag. Mirrors the ems01/ems02 migrations'
shape: set-based SQL only, no ORM. See server/app/matcha/services/inventory/
CLAUDE.md for the full feature spec.

NOTE: the alembic history on this branch has multiple leaves; down_revision
is set to `ems02`, a verified leaf at authoring time (no other migration's
down_revision points to it as of 2026-08-02). Confirm the correct head for
your environment before `alembic upgrade` if time has passed.

Revision ID: inventory01
Revises: ems02
Create Date: 2026-08-02
"""

from alembic import op

revision = "inventory01"
down_revision = "ems02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE inventory_items (
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
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_items_name
        ON inventory_items (company_id, normalized_name) WHERE archived_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE inventory_movements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('out','in','stockout','adjust')),
            quantity NUMERIC,
            quantity_delta NUMERIC,
            quantity_estimated BOOLEAN NOT NULL DEFAULT FALSE,
            note TEXT,
            narrative TEXT NOT NULL,
            clarify_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            clarify_rounds SMALLINT NOT NULL DEFAULT 0,
            amended_by UUID REFERENCES users(id) ON DELETE SET NULL,
            amended_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_movements_message
        ON inventory_movements (source_message_id, item_id) WHERE source_message_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_movements_clarify
        ON inventory_movements (clarify_message_id) WHERE clarify_message_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX idx_inventory_movements_company ON inventory_movements (company_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_inventory_movements_item ON inventory_movements (item_id, created_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE inventory_orders (
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
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_orders_confirm
        ON inventory_orders (confirm_message_id) WHERE confirm_message_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uniq_inventory_orders_open
        ON inventory_orders (item_id) WHERE status = 'queued'
        """
    )
    op.execute(
        "CREATE INDEX idx_inventory_orders_company ON inventory_orders (company_id, status, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS inventory_orders")
    op.execute("DROP TABLE IF EXISTS inventory_movements")
    op.execute("DROP TABLE IF EXISTS inventory_items")
