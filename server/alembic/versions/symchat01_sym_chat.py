"""Sym-chat: intent-shaped micro group chats on the matcha-work /work surface.

A sym-chat has an objective (find a meeting time, pick a place). Each
participant types in a private tunnel only they and the assistant see; a
flash-lite call re-derives that participant's structured stance, and a
deterministic per-kind aggregator recomputes the shared consensus "shape".
Material shape changes append a line to the shared feed.

- `mw_sym_chats`: one row per chat — kind, objective, materialized config,
  current shape, and the resolution once consensus is reached.
- `mw_sym_chat_participants`: membership + the participant's current stance.
- `mw_sym_chat_messages`: the private tunnels (keyed by participant user_id).
- `mw_sym_chat_updates`: the shared shape-update feed, sequenced per chat.

Additive. Nothing reads these tables unless the `sym_chat` flag is on.

Revision ID: symchat01
Revises: mcpconn01
"""

from alembic import op


revision = "symchat01"
down_revision = "mcpconn01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_sym_chats (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('schedule', 'decide')),
            title VARCHAR(120) NOT NULL,
            objective TEXT NOT NULL DEFAULT '',
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'resolved', 'cancelled')),
            shape JSONB NOT NULL DEFAULT '{}'::jsonb,
            resolution JSONB,
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_sym_chats_company_created
            ON mw_sym_chats (company_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_sym_chat_participants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sym_chat_id UUID NOT NULL REFERENCES mw_sym_chats(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            stance JSONB,
            responded_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (sym_chat_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_sym_chat_participants_user
            ON mw_sym_chat_participants (user_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_sym_chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sym_chat_id UUID NOT NULL REFERENCES mw_sym_chats(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_sym_chat_messages_tunnel
            ON mw_sym_chat_messages (sym_chat_id, user_id, created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_sym_chat_updates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sym_chat_id UUID NOT NULL REFERENCES mw_sym_chats(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            content TEXT NOT NULL,
            shape JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (sym_chat_id, seq)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_sym_chat_updates")
    op.execute("DROP TABLE IF EXISTS mw_sym_chat_messages")
    op.execute("DROP TABLE IF EXISTS mw_sym_chat_participants")
    op.execute("DROP TABLE IF EXISTS mw_sym_chats")
