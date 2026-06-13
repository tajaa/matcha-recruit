"""Cappe messages — lightweight two-way inbox between a creator and clients.

A thread is a conversation with one client (by email), optionally linked to a
booking or order. The creator replies from the dashboard; the client reads and
replies via a token-gated public page (link emailed to them). Email-backed, no
WebSocket — most creator↔client comms is async.

Additive. Apply to dev AND prod (legacy :5433 + RDS pre-cutover).

Revision ID: zzzzcappe07
Revises: zzzzcappe06
"""
from alembic import op

revision = "zzzzcappe07"
down_revision = "zzzzcappe06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_threads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            access_token UUID NOT NULL DEFAULT gen_random_uuid(),  -- unguessable client link
            client_email VARCHAR(320) NOT NULL,
            client_name VARCHAR(255),
            subject VARCHAR(300),
            status VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'closed')),
            booking_id UUID REFERENCES cappe_bookings(id) ON DELETE SET NULL,
            order_id UUID REFERENCES cappe_orders(id) ON DELETE SET NULL,
            owner_unread INTEGER NOT NULL DEFAULT 0,
            client_unread INTEGER NOT NULL DEFAULT 0,
            last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_threads_token ON cappe_threads(access_token)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_threads_site_recent "
        "ON cappe_threads(site_id, last_message_at DESC)"
    )
    # One open thread per (site, client email) keeps the inbox tidy; closing a
    # thread frees a new one to be opened later.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_threads_site_email_open "
        "ON cappe_threads(site_id, lower(client_email)) WHERE status = 'open'"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES cappe_threads(id) ON DELETE CASCADE,
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            sender VARCHAR(10) NOT NULL CHECK (sender IN ('owner', 'client')),
            body TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_messages_thread "
        "ON cappe_messages(thread_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_messages")
    op.execute("DROP TABLE IF EXISTS cappe_threads")
