"""Add client_message_id to channel_messages for server-side idempotency.

Revision ID: zzzz_b03_chmsg_cmid
Revises: zzzz_b02_taskhist
Create Date: 2026-05-19

Client-side dedup already handles most duplicate-broadcast races (the WS
echo carries client_message_id; the sender reconciles a pending row with
its echo by matching cmid; receivers dedup by server id). But a
double-send from the client — manual retry, double-click, flaky WS — used
to produce two `channel_messages` rows with two different server UUIDs,
so the second echo arrives as a fresh id and falls through to id-dedup
as a duplicate.

This migration adds a nullable `client_message_id UUID` column plus a
partial unique index on `(sender_id, client_message_id)`. The route
handler upserts via `ON CONFLICT (sender_id, client_message_id) DO
UPDATE SET id = channel_messages.id RETURNING ...` so a retried send
returns the original row and re-broadcasts with the same server id —
client dedup-by-id then catches it. End-to-end idempotent.

Notes:
- Partial index (`WHERE client_message_id IS NOT NULL`) lets legacy rows
  stay NULL without colliding with one another.
- Created CONCURRENTLY so it doesn't block writers on a busy table.
  Requires autocommit_block — CREATE INDEX CONCURRENTLY cannot run
  inside a transaction.
"""
from alembic import op


revision = "zzzz_b03_chmsg_cmid"
down_revision = "zzzz_b02_taskhist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE channel_messages
        ADD COLUMN IF NOT EXISTS client_message_id UUID
        """
    )
    # CONCURRENTLY can't run inside a transaction; pop out to autocommit.
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
                uniq_channel_messages_sender_cmid
            ON channel_messages (sender_id, client_message_id)
            WHERE client_message_id IS NOT NULL
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uniq_channel_messages_sender_cmid")
    op.execute("ALTER TABLE channel_messages DROP COLUMN IF EXISTS client_message_id")
