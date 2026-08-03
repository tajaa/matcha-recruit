"""Location-scoped Ops: channels.location_id, ems_events.location_id,
inventory_items.location_id + per-location item uniqueness.

A channel bound to a business_locations row scopes @huume dispatch in that
channel: EMS events are stamped with the store, inventory resolves against
the store's own catalog, schedule-chat defaults the location. Items:
NULLS NOT DISTINCT makes (company, NULL, name) collide exactly like the old
(company, name) index, so existing all-NULL data needs no dedupe pass.

Requires PostgreSQL 15+ (NULLS NOT DISTINCT). Prod is PG 15.18.

ON DELETE SET NULL on inventory_items.location_id can violate the unique
index if a deleted location's item names collide with another store's (or
company-wide) item. `delete_location` (compliance_service/_locations.py)
now blocks the delete at the app layer whenever any channel/inventory_item/
ems_event still references the location, pointing the caller at
deactivation (is_active=false) instead — but that is an application-level
guard, not a DB constraint, so anything that DELETEs business_locations
directly (a script, a future admin tool) can still hit the same 23505.

NOTE: the alembic history on this branch has multiple heads; down_revision
is `empavail01`, a verified leaf at authoring time (2026-08-02).

Revision ID: oploc01
Revises: empavail01
"""
from alembic import op

revision = "oploc01"
down_revision = "empavail01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS location_id UUID "
        "REFERENCES business_locations(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_channels_location "
        "ON channels(location_id) WHERE location_id IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS location_id UUID "
        "REFERENCES business_locations(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS location_id UUID "
        "REFERENCES business_locations(id) ON DELETE SET NULL"
    )
    op.execute("DROP INDEX IF EXISTS uniq_inventory_items_name")
    op.execute(
        "CREATE UNIQUE INDEX uniq_inventory_items_name "
        "ON inventory_items (company_id, location_id, normalized_name) "
        "NULLS NOT DISTINCT WHERE archived_at IS NULL"
    )


def downgrade():
    # Recreating the narrower index fails if per-location duplicate names
    # were created after upgrade; dedupe/archive those rows manually first.
    op.execute("DROP INDEX IF EXISTS uniq_inventory_items_name")
    op.execute(
        "CREATE UNIQUE INDEX uniq_inventory_items_name "
        "ON inventory_items (company_id, normalized_name) WHERE archived_at IS NULL"
    )
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS location_id")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS location_id")
    op.execute("DROP INDEX IF EXISTS idx_channels_location")
    op.execute("ALTER TABLE channels DROP COLUMN IF EXISTS location_id")
