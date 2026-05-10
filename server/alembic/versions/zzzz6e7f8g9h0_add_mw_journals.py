"""Add mw_journals + mw_journal_entries + mw_journal_collaborators.

Revision ID: zzzz6e7f8g9h0
Revises: zzzz5d6e7f8g9
Create Date: 2026-05-09
"""
from alembic import op


revision = "zzzz6e7f8g9h0"
down_revision = "zzzz5d6e7f8g9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_journals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id),
            title VARCHAR(255) NOT NULL DEFAULT 'Untitled Journal',
            description TEXT,
            color VARCHAR(20),
            icon VARCHAR(64),
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_mw_journals_created_by ON mw_journals(created_by);
        CREATE INDEX IF NOT EXISTS idx_mw_journals_company_id ON mw_journals(company_id);

        CREATE TABLE IF NOT EXISTS mw_journal_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            journal_id UUID NOT NULL REFERENCES mw_journals(id) ON DELETE CASCADE,
            author_id UUID NOT NULL REFERENCES users(id),
            title VARCHAR(255),
            content TEXT NOT NULL DEFAULT '',
            entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_mw_journal_entries_journal_date
            ON mw_journal_entries(journal_id, entry_date DESC, created_at DESC);

        CREATE TABLE IF NOT EXISTS mw_journal_collaborators (
            journal_id UUID NOT NULL REFERENCES mw_journals(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invited_by UUID REFERENCES users(id),
            role VARCHAR(20) NOT NULL DEFAULT 'collaborator'
                CHECK (role IN ('owner', 'collaborator')),
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'pending', 'removed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (journal_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_mw_journal_collaborators_user
            ON mw_journal_collaborators(user_id, status);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS mw_journal_collaborators;
        DROP TABLE IF EXISTS mw_journal_entries;
        DROP TABLE IF EXISTS mw_journals;
    """)
