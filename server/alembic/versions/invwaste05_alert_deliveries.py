"""Idempotency records and scheduler row for inventory waste alerts."""
from alembic import op

revision = "invwaste05"
down_revision = "invwaste04"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS inventory_waste_alert_deliveries (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(), company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL, alert_date DATE NOT NULL,
        alert_kind VARCHAR(30) NOT NULL CHECK (alert_kind IN ('expiring','waste_spike','par_applied')),
        recipient_email VARCHAR(255), channel_id UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_waste_alert_deliveries
        ON inventory_waste_alert_deliveries (company_id, location_id, alert_date, alert_kind, recipient_email) NULLS NOT DISTINCT""")
    for key, name, description in (
        ('inventory_par_sweep', 'Inventory par sweep', 'Apply guarded predictive par recommendations'),
    ):
        op.execute(f"INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle) VALUES ('{key}', '{name}', '{description}', FALSE, 200) ON CONFLICT (task_key) DO NOTHING")

def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key='inventory_par_sweep'")
    op.execute("DROP INDEX IF EXISTS uniq_inventory_waste_alert_deliveries")
    op.execute("DROP TABLE IF EXISTS inventory_waste_alert_deliveries")
