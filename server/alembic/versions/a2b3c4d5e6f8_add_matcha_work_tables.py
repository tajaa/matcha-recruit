"""add matcha work tables

Revision ID: a2b3c4d5e6f8
Revises: f4e5d6c7b8a9
Create Date: 2026-02-24
"""

from alembic import op


revision = "a2b3c4d5e6f8"
down_revision = "f4e5d6c7b8a9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_threads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL DEFAULT 'Untitled Offer Letter',
            task_type VARCHAR(40) NOT NULL DEFAULT 'offer_letter'
                CHECK (task_type IN ('offer_letter')),
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'finalized', 'archived')),
            current_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            version INTEGER NOT NULL DEFAULT 0,
            linked_offer_letter_id UUID REFERENCES offer_letters(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_threads_company_id ON mw_threads(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_threads_created_by ON mw_threads(created_by)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_threads_company_status ON mw_threads(company_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            version_created INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_messages_thread_id ON mw_messages(thread_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_messages_thread_created_at ON mw_messages(thread_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_document_versions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            state_json JSONB NOT NULL,
            diff_summary TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(thread_id, version)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_document_versions_thread_id ON mw_document_versions(thread_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_pdf_cache (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            pdf_url TEXT NOT NULL,
            is_draft BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(thread_id, version, is_draft)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_pdf_cache_thread_id ON mw_pdf_cache(thread_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_pdf_cache_thread_id")
    op.execute("DROP TABLE IF EXISTS mw_pdf_cache")

    op.execute("DROP INDEX IF EXISTS idx_mw_document_versions_thread_id")
    op.execute("DROP TABLE IF EXISTS mw_document_versions")

    op.execute("DROP INDEX IF EXISTS idx_mw_messages_thread_created_at")
    op.execute("DROP INDEX IF EXISTS idx_mw_messages_thread_id")
    op.execute("DROP TABLE IF EXISTS mw_messages")

    op.execute("DROP INDEX IF EXISTS idx_mw_threads_company_status")
    op.execute("DROP INDEX IF EXISTS idx_mw_threads_created_by")
    op.execute("DROP INDEX IF EXISTS idx_mw_threads_company_id")
    op.execute("DROP TABLE IF EXISTS mw_threads")
