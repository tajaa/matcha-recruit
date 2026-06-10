"""Enforce one active call / broadcast per channel via partial UNIQUE indexes.

Closes the TOCTOU race in channel_calls.start_call / channel_broadcasts.start
(read-then-insert with no constraint). Combined with the per-channel
pg_advisory_xact_lock in those endpoints, this guarantees a channel can never
hold two live calls, two live broadcasts, or a call+broadcast simultaneously.

Replaces the non-unique idx_channel_calls_active with a UNIQUE partial index.

Revision ID: chcallrace01
Revises: chcalls01
Create Date: 2026-06-10
"""
from alembic import op


revision = "chcallrace01"
down_revision = "chcalls01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Dedupe any pre-existing active duplicates (keep the earliest-started
    #    row per channel, close the rest) so the UNIQUE index can be created.
    op.execute("""
        UPDATE channel_calls c SET ended_at = NOW()
        WHERE ended_at IS NULL
          AND id <> (
            SELECT id FROM channel_calls c2
            WHERE c2.channel_id = c.channel_id AND c2.ended_at IS NULL
            ORDER BY started_at ASC, id ASC
            LIMIT 1
          )
    """)
    op.execute("""
        UPDATE channel_broadcasts b SET ended_at = NOW()
        WHERE ended_at IS NULL
          AND id <> (
            SELECT id FROM channel_broadcasts b2
            WHERE b2.channel_id = b.channel_id AND b2.ended_at IS NULL
            ORDER BY started_at ASC, id ASC
            LIMIT 1
          )
    """)

    # 2) Replace the non-unique active index with a UNIQUE partial index.
    op.execute("DROP INDEX IF EXISTS idx_channel_calls_active")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_calls_one_active
            ON channel_calls(channel_id) WHERE ended_at IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_broadcasts_one_active
            ON channel_broadcasts(channel_id) WHERE ended_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_broadcasts_one_active")
    op.execute("DROP INDEX IF EXISTS idx_channel_calls_one_active")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_calls_active
            ON channel_calls(channel_id) WHERE ended_at IS NULL
    """)
