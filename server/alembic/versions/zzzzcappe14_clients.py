"""cappe: import-able client directory (branch-aware)

Adds a `cappe_clients` table so businesses can port in their existing clientele
(CSV import / manual add) as a first-class touchpoint, each optionally mapped to
a branch (`location_id`). The Clients view UNIONs this table into its live
roll-up across orders/bookings/subscribers/threads, so imported clients show up
alongside organic ones and never drift.

`location_id` is NULLABLE (NULL = main / all locations), mirroring the
zzzzcappe13 multi-location convention. Email is unique per site.

Revision ID: zzzzcappe14
Revises: zzzzcappe13
Create Date: 2026-06-15
"""
from alembic import op

revision = "zzzzcappe14"
down_revision = "zzzzcappe13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_clients (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            email VARCHAR(320) NOT NULL,
            name VARCHAR(255),
            phone VARCHAR(40),
            location_id UUID REFERENCES cappe_locations(id) ON DELETE SET NULL,
            notes TEXT,
            tags TEXT[] NOT NULL DEFAULT '{}',
            source VARCHAR(40) NOT NULL DEFAULT 'import'
                CHECK (source IN ('import', 'manual')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT cappe_clients_site_email_unique UNIQUE (site_id, email)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_clients_site ON cappe_clients(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_clients_location ON cappe_clients(location_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_clients")
