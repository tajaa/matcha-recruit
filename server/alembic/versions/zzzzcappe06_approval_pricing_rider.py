"""Cappe booking approval queue + dynamic time pricing + creator rider.

Three features, one additive migration:
  1. Approval queue — `requires_approval` on booking types & products; bookings
     and orders can land needing the creator's accept/decline. Adds `declined`
     to the booking/order status CHECKs, plus `approved_at` / `decline_reason`.
  2. Dynamic pricing — booking types gain `pricing_mode` (flat | hourly); new
     `cappe_rate_rules` holds time-window multipliers (e.g. after 8pm = 2x).
     Bookings store the computed `quoted_price_cents`.
  3. Rider — `cappe_rider_items` (Pro, personal creators) defines standard
     requirements shown to buyers; a booking snapshots the rider it agreed to.

Additive + idempotent. Apply to dev AND prod (legacy :5433 + RDS pre-cutover).

Revision ID: zzzzcappe06
Revises: zzzzcappe05
"""
from alembic import op

revision = "zzzzcappe06"
down_revision = "zzzzcappe05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Approval flags ------------------------------------------------------
    op.execute(
        "ALTER TABLE cappe_booking_types "
        "ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE cappe_products "
        "ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN NOT NULL DEFAULT false"
    )

    # 2. Pricing -------------------------------------------------------------
    # pricing_mode: 'flat' = price_cents is the whole-booking price (today's
    # behavior); 'hourly' = price_cents is the base $/hr, multiplied by any
    # matching rate rule for each segment of the booked time.
    op.execute(
        "ALTER TABLE cappe_booking_types "
        "ADD COLUMN IF NOT EXISTS pricing_mode VARCHAR(10) NOT NULL DEFAULT 'flat'"
    )
    op.execute(
        "ALTER TABLE cappe_booking_types DROP CONSTRAINT IF EXISTS cappe_booking_types_pricing_mode_check"
    )
    op.execute(
        "ALTER TABLE cappe_booking_types "
        "ADD CONSTRAINT cappe_booking_types_pricing_mode_check "
        "CHECK (pricing_mode IN ('flat', 'hourly'))"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_rate_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            booking_type_id UUID REFERENCES cappe_booking_types(id) ON DELETE CASCADE,  -- NULL = all types
            label VARCHAR(120) NOT NULL,
            weekday SMALLINT CHECK (weekday BETWEEN 0 AND 6),  -- NULL = every day (Mon=0..Sun=6)
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            multiplier NUMERIC(5,2) NOT NULL DEFAULT 1.0 CHECK (multiplier >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (end_time > start_time)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_rate_rules_site ON cappe_rate_rules(site_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_rate_rules_type ON cappe_rate_rules(booking_type_id)"
    )

    # 3. Rider ---------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_rider_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            label VARCHAR(200) NOT NULL,
            detail TEXT,
            is_required BOOLEAN NOT NULL DEFAULT true,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_rider_items_site ON cappe_rider_items(site_id)")

    # 4. Booking columns + status set ---------------------------------------
    op.execute(
        """
        ALTER TABLE cappe_bookings
            ADD COLUMN IF NOT EXISTS requires_approval   BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS quoted_price_cents  INTEGER,
            ADD COLUMN IF NOT EXISTS approved_at         TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS decline_reason      TEXT,
            ADD COLUMN IF NOT EXISTS rider_snapshot      JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS rider_acknowledged  BOOLEAN NOT NULL DEFAULT false
        """
    )
    # Awaiting-approval bookings reuse 'pending'; add 'declined' for creator rejects.
    op.execute("ALTER TABLE cappe_bookings DROP CONSTRAINT IF EXISTS cappe_bookings_status_check")
    op.execute(
        "ALTER TABLE cappe_bookings ADD CONSTRAINT cappe_bookings_status_check "
        "CHECK (status IN ('pending', 'confirmed', 'declined', 'cancelled', 'completed'))"
    )

    # 5. Order columns + status set -----------------------------------------
    op.execute(
        """
        ALTER TABLE cappe_orders
            ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS approved_at       TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS decline_reason    TEXT
        """
    )
    op.execute("ALTER TABLE cappe_orders DROP CONSTRAINT IF EXISTS cappe_orders_status_check")
    op.execute(
        "ALTER TABLE cappe_orders ADD CONSTRAINT cappe_orders_status_check "
        "CHECK (status IN ('pending', 'paid', 'fulfilled', 'cancelled', 'refunded', 'declined'))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_rider_items")
    op.execute("DROP TABLE IF EXISTS cappe_rate_rules")
    op.execute("ALTER TABLE cappe_orders DROP CONSTRAINT IF EXISTS cappe_orders_status_check")
    op.execute(
        "ALTER TABLE cappe_orders ADD CONSTRAINT cappe_orders_status_check "
        "CHECK (status IN ('pending', 'paid', 'fulfilled', 'cancelled', 'refunded'))"
    )
    op.execute(
        """
        ALTER TABLE cappe_orders
            DROP COLUMN IF EXISTS requires_approval,
            DROP COLUMN IF EXISTS approved_at,
            DROP COLUMN IF EXISTS decline_reason
        """
    )
    op.execute("ALTER TABLE cappe_bookings DROP CONSTRAINT IF EXISTS cappe_bookings_status_check")
    op.execute(
        "ALTER TABLE cappe_bookings ADD CONSTRAINT cappe_bookings_status_check "
        "CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed'))"
    )
    op.execute(
        """
        ALTER TABLE cappe_bookings
            DROP COLUMN IF EXISTS requires_approval,
            DROP COLUMN IF EXISTS quoted_price_cents,
            DROP COLUMN IF EXISTS approved_at,
            DROP COLUMN IF EXISTS decline_reason,
            DROP COLUMN IF EXISTS rider_snapshot,
            DROP COLUMN IF EXISTS rider_acknowledged
        """
    )
    op.execute("ALTER TABLE cappe_booking_types DROP CONSTRAINT IF EXISTS cappe_booking_types_pricing_mode_check")
    op.execute(
        """
        ALTER TABLE cappe_booking_types
            DROP COLUMN IF EXISTS requires_approval,
            DROP COLUMN IF EXISTS pricing_mode
        """
    )
    op.execute("ALTER TABLE cappe_products DROP COLUMN IF EXISTS requires_approval")
