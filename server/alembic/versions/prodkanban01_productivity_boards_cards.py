"""Personal productivity kanban — user-scoped boards + cards.

`mw_productivity_boards` (a user's personal boards) and `mw_productivity_cards`
(todo / in_progress / done). Cards may back-link to a journal via
`source_journal_id` + `source_excerpt` when created from a text selection.

Revision ID: prodkanban01
Revises: jrnl2nb01
Create Date: 2026-06-10
"""
from alembic import op


revision = "prodkanban01"
down_revision = "jrnl2nb01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_productivity_boards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL DEFAULT 'My To-Dos',
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_prod_boards_user ON mw_productivity_boards(user_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_productivity_cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            board_id UUID NOT NULL REFERENCES mw_productivity_boards(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            notes TEXT,
            board_column VARCHAR(20) NOT NULL DEFAULT 'todo'
                CHECK (board_column IN ('todo', 'in_progress', 'done')),
            position INTEGER NOT NULL DEFAULT 0,
            source_journal_id UUID REFERENCES mw_journals(id) ON DELETE SET NULL,
            source_excerpt TEXT,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_prod_cards_board ON mw_productivity_cards(board_id, board_column, position)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_productivity_cards")
    op.execute("DROP TABLE IF EXISTS mw_productivity_boards")
