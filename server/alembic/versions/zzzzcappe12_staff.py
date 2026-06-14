"""Cappe staff / stylist booking.

Salons add staff members; a service maps to who offers it (cappe_staff_services).
A booking and an availability window can belong to a staff member, so a customer
can book a specific stylist or "any available". Existing single-calendar sites
are unchanged: a service with NO staff mapping stays the shared-calendar path
(staff_id NULL). Booking types also gain a service `category` + `buffer_minutes`.

The double-book guard is rebuilt to include staff_id — COALESCE'd to a sentinel
so legacy NULL-staff bookings are still guarded (NULLs are otherwise distinct in
a unique index, which would silently drop the legacy guard).

Revision ID: zzzzcappe12
Revises: zzzzcappe11
"""
from alembic import op

revision = "zzzzcappe12"
down_revision = "zzzzcappe11"
branch_labels = None
depends_on = None

_SENTINEL = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_staff (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            bio TEXT,
            image_url TEXT,
            active BOOLEAN NOT NULL DEFAULT true,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_staff_site ON cappe_staff(site_id, active, sort_order)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_staff_services (
            staff_id UUID NOT NULL REFERENCES cappe_staff(id) ON DELETE CASCADE,
            booking_type_id UUID NOT NULL REFERENCES cappe_booking_types(id) ON DELETE CASCADE,
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            PRIMARY KEY (staff_id, booking_type_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_staff_services_type ON cappe_staff_services(booking_type_id)")

    op.execute("ALTER TABLE cappe_bookings ADD COLUMN IF NOT EXISTS staff_id UUID REFERENCES cappe_staff(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_bookings_staff ON cappe_bookings(staff_id)")
    op.execute("ALTER TABLE cappe_availability ADD COLUMN IF NOT EXISTS staff_id UUID REFERENCES cappe_staff(id) ON DELETE CASCADE")

    op.execute("ALTER TABLE cappe_booking_types ADD COLUMN IF NOT EXISTS category VARCHAR(120)")
    op.execute(
        "ALTER TABLE cappe_booking_types ADD COLUMN IF NOT EXISTS buffer_minutes INTEGER NOT NULL DEFAULT 0 "
        "CHECK (buffer_minutes >= 0)"
    )

    # Rebuild the double-book guard to be staff-aware. NULL staff (legacy /
    # unstaffed services) collapse to a sentinel so they keep ONE shared-calendar
    # key, while real staff each get their own per-staff slot.
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_no_doublebook")
    op.execute(
        "CREATE UNIQUE INDEX idx_cappe_bookings_no_doublebook "
        "ON cappe_bookings(site_id, booking_type_id, COALESCE(staff_id, '%s'::uuid), starts_at) "
        "WHERE status IN ('pending', 'confirmed')" % _SENTINEL
    )

    # Extend availability uniqueness to include staff_id (two stylists may hold
    # the same window). Drop the original table UNIQUE (auto-named) by lookup,
    # then add a plain unique index covering staff_id.
    op.execute(
        """
        DO $$
        DECLARE c text;
        BEGIN
            SELECT conname INTO c FROM pg_constraint
             WHERE conrelid = 'cappe_availability'::regclass AND contype = 'u' LIMIT 1;
            IF c IS NOT NULL THEN EXECUTE 'ALTER TABLE cappe_availability DROP CONSTRAINT ' || quote_ident(c); END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_availability_unique "
        "ON cappe_availability(site_id, weekday, start_time, end_time, booking_type_id, staff_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_availability_unique")
    op.execute(
        "ALTER TABLE cappe_availability ADD CONSTRAINT cappe_availability_site_id_weekday_start_time_end_time_booki_key "
        "UNIQUE (site_id, weekday, start_time, end_time, booking_type_id)"
    )
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_no_doublebook")
    op.execute(
        "CREATE UNIQUE INDEX idx_cappe_bookings_no_doublebook "
        "ON cappe_bookings(site_id, booking_type_id, starts_at) WHERE status IN ('pending', 'confirmed')"
    )
    op.execute("ALTER TABLE cappe_booking_types DROP COLUMN IF EXISTS buffer_minutes")
    op.execute("ALTER TABLE cappe_booking_types DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE cappe_availability DROP COLUMN IF EXISTS staff_id")
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_staff")
    op.execute("ALTER TABLE cappe_bookings DROP COLUMN IF EXISTS staff_id")
    op.execute("DROP TABLE IF EXISTS cappe_staff_services")
    op.execute("DROP TABLE IF EXISTS cappe_staff")
