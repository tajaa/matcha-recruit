"""Add Cappe commerce + site surfaces: shop, newsletter, forms, bookings, blog.

All per-site (FK site_id -> cappe_sites ON DELETE CASCADE), following the
zzzzcappe01 conventions. Payments + email send are stubbed at the app layer;
these tables model the full data. order_items carry a denormalized site_id (so
an item can never reference a product from another site) and snapshot
title/price (so editing/deleting a product never corrupts order history).

Revision ID: zzzzcappe02
Revises: zzzzcappe01
Create Date: 2026-06-11
"""
from alembic import op


revision = "zzzzcappe02"
down_revision = "zzzzcappe01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Shop -------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_products (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            price_cents INTEGER NOT NULL DEFAULT 0 CHECK (price_cents >= 0),
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            image_url TEXT,
            sku VARCHAR(120),
            inventory INTEGER,                       -- NULL = unlimited
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('active', 'draft', 'archived')),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_products_site ON cappe_products(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_products_site_status ON cappe_products(site_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_products_site_sort ON cappe_products(site_id, sort_order)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            customer_email VARCHAR(320),
            customer_name VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'paid', 'fulfilled', 'cancelled', 'refunded')),
            subtotal_cents INTEGER NOT NULL DEFAULT 0 CHECK (subtotal_cents >= 0),
            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
            payment_ref VARCHAR(255),
            note TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_orders_site ON cappe_orders(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_orders_site_status ON cappe_orders(site_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_orders_site_created ON cappe_orders(site_id, created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_order_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES cappe_orders(id) ON DELETE CASCADE,
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            product_id UUID REFERENCES cappe_products(id) ON DELETE SET NULL,
            title VARCHAR(255) NOT NULL,             -- snapshot of product name
            unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_order_items_order ON cappe_order_items(order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_order_items_product ON cappe_order_items(product_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_order_items_site ON cappe_order_items(site_id)")

    # --- Newsletter -------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_subscribers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            email VARCHAR(320) NOT NULL,
            name VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'subscribed'
                CHECK (status IN ('subscribed', 'unsubscribed', 'bounced', 'pending')),
            source VARCHAR(60) NOT NULL DEFAULT 'website',
            unsubscribe_token VARCHAR(64) NOT NULL DEFAULT replace(gen_random_uuid()::text, '-', ''),
            unsubscribed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (site_id, email),
            UNIQUE (unsubscribe_token)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_subscribers_site ON cappe_subscribers(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_subscribers_site_status ON cappe_subscribers(site_id, status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            subject VARCHAR(500) NOT NULL,
            body_html TEXT,
            from_name VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'scheduled', 'sending', 'sent', 'cancelled')),
            scheduled_at TIMESTAMPTZ,
            sent_at TIMESTAMPTZ,
            recipient_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_campaigns_site ON cappe_campaigns(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_campaigns_site_status ON cappe_campaigns(site_id, status)")

    # --- Forms ------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_forms (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(160) NOT NULL,
            fields JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{key,label,type,required}]
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'draft', 'archived')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (site_id, slug)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_forms_site ON cappe_forms(site_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_form_submissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            form_id UUID NOT NULL REFERENCES cappe_forms(id) ON DELETE CASCADE,
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            submitter_email VARCHAR(320),
            is_read BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_form_subs_form ON cappe_form_submissions(form_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_form_subs_site ON cappe_form_submissions(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_form_subs_site_read ON cappe_form_submissions(site_id, is_read)")

    # --- Bookings ---------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_booking_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            duration_minutes INTEGER NOT NULL DEFAULT 30 CHECK (duration_minutes > 0),
            price_cents INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'draft', 'archived')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_booking_types_site ON cappe_booking_types(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_booking_types_site_status ON cappe_booking_types(site_id, status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_availability (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            booking_type_id UUID REFERENCES cappe_booking_types(id) ON DELETE CASCADE,  -- NULL = all types
            weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (end_time > start_time),
            UNIQUE (site_id, weekday, start_time, end_time, booking_type_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_availability_site ON cappe_availability(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_availability_site_weekday ON cappe_availability(site_id, weekday)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_bookings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            booking_type_id UUID REFERENCES cappe_booking_types(id) ON DELETE SET NULL,
            customer_name VARCHAR(255),
            customer_email VARCHAR(320),
            starts_at TIMESTAMPTZ NOT NULL,
            ends_at TIMESTAMPTZ NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed')),
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_bookings_site ON cappe_bookings(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_bookings_site_status ON cappe_bookings(site_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_bookings_site_starts ON cappe_bookings(site_id, starts_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_bookings_type ON cappe_bookings(booking_type_id)")
    # Cheap structural double-book guard: no two live bookings share the exact slot.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_bookings_no_doublebook "
        "ON cappe_bookings(site_id, booking_type_id, starts_at) "
        "WHERE status IN ('pending', 'confirmed')"
    )

    # --- Blog -------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_posts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            slug VARCHAR(160) NOT NULL,
            excerpt TEXT,
            body TEXT,
            cover_image_url TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'archived')),
            published_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (site_id, slug)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_posts_site ON cappe_posts(site_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cappe_posts_site_status ON cappe_posts(site_id, status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_posts_site_published ON cappe_posts(site_id, published_at DESC) "
        "WHERE status = 'published'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_posts")
    op.execute("DROP TABLE IF EXISTS cappe_bookings")
    op.execute("DROP TABLE IF EXISTS cappe_availability")
    op.execute("DROP TABLE IF EXISTS cappe_booking_types")
    op.execute("DROP TABLE IF EXISTS cappe_form_submissions")
    op.execute("DROP TABLE IF EXISTS cappe_forms")
    op.execute("DROP TABLE IF EXISTS cappe_campaigns")
    op.execute("DROP TABLE IF EXISTS cappe_subscribers")
    op.execute("DROP TABLE IF EXISTS cappe_order_items")
    op.execute("DROP TABLE IF EXISTS cappe_orders")
    op.execute("DROP TABLE IF EXISTS cappe_products")
