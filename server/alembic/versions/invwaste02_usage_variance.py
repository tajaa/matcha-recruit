"""Persist per-item audit and theoretical-usage variance."""

from alembic import op


revision = "invwaste02"
down_revision = "invwaste01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_audit_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES inventory_audit_runs(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            expected NUMERIC,
            counted NUMERIC NOT NULL,
            variance NUMERIC,
            unit_cost NUMERIC,
            variance_value NUMERIC,
            theoretical_usage NUMERIC,
            actual_usage NUMERIC,
            usage_variance NUMERIC,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (run_id, item_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_audit_lines_item
        ON inventory_audit_lines (item_id, created_at DESC)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_inventory_audit_lines_item")
    op.execute("DROP TABLE IF EXISTS inventory_audit_lines")
