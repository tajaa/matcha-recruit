"""Cappe existing-client booking suggestion access.

Email links are single-use capabilities; both link and session secrets are
stored only as SHA-256 hashes. Sessions are site-scoped so a client approved
for one business cannot use suggestions for another.

Revision ID: cappeaiaccess01
Revises: ems04, mwperm02
"""
from alembic import op


revision = "cappeaiaccess01"
down_revision = ("ems04", "mwperm02")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_booking_suggestion_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            client_email VARCHAR(320) NOT NULL,
            token_hash CHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (client_email = lower(btrim(client_email))),
            UNIQUE (site_id, client_email)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cappe_booking_suggestion_links_active
            ON cappe_booking_suggestion_links (site_id, client_email, expires_at)
            WHERE used_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_booking_suggestion_links_expiry "
        "ON cappe_booking_suggestion_links (expires_at)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_booking_suggestion_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            client_email VARCHAR(320) NOT NULL,
            token_hash CHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (client_email = lower(btrim(client_email))),
            UNIQUE (site_id, client_email)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cappe_booking_suggestion_sessions_active
            ON cappe_booking_suggestion_sessions (site_id, token_hash, expires_at)
            WHERE revoked_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_booking_suggestion_sessions_expiry "
        "ON cappe_booking_suggestion_sessions (expires_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_clients_site_email_lower "
        "ON cappe_clients (site_id, lower(email))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_bookings_site_email_lower "
        "ON cappe_bookings (site_id, lower(customer_email)) "
        "WHERE customer_email IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_orders_site_paid_email_lower "
        "ON cappe_orders (site_id, lower(customer_email)) "
        "WHERE customer_email IS NOT NULL AND status IN ('paid', 'fulfilled')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_orders_site_paid_email_lower")
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_site_email_lower")
    op.execute("DROP INDEX IF EXISTS idx_cappe_clients_site_email_lower")
    op.execute("DROP INDEX IF EXISTS idx_cappe_booking_suggestion_sessions_expiry")
    op.execute("DROP INDEX IF EXISTS idx_cappe_booking_suggestion_links_expiry")
    op.execute("DROP TABLE IF EXISTS cappe_booking_suggestion_sessions")
    op.execute("DROP TABLE IF EXISTS cappe_booking_suggestion_links")
