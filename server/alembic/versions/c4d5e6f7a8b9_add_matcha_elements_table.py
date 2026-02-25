"""add matcha elements table

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-02-25
"""

from alembic import op


revision = "c4d5e6f7a8b9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_elements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL UNIQUE REFERENCES mw_threads(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            element_type VARCHAR(40) NOT NULL DEFAULT 'offer_letter'
                CHECK (element_type IN ('offer_letter')),
            title VARCHAR(255) NOT NULL DEFAULT 'Untitled Chat',
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'finalized', 'archived')),
            state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            version INTEGER NOT NULL DEFAULT 0,
            linked_offer_letter_id UUID REFERENCES offer_letters(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_elements_company_status ON mw_elements(company_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_elements_created_by ON mw_elements(created_by)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_elements_thread_id ON mw_elements(thread_id)"
    )

    op.execute(
        """
        INSERT INTO mw_elements (
            thread_id,
            company_id,
            created_by,
            element_type,
            title,
            status,
            state_json,
            version,
            linked_offer_letter_id,
            created_at,
            updated_at
        )
        SELECT
            t.id,
            t.company_id,
            t.created_by,
            t.task_type,
            t.title,
            t.status,
            t.current_state,
            t.version,
            t.linked_offer_letter_id,
            t.created_at,
            t.updated_at
        FROM mw_threads t
        ON CONFLICT (thread_id) DO UPDATE
        SET
            company_id = EXCLUDED.company_id,
            created_by = EXCLUDED.created_by,
            element_type = EXCLUDED.element_type,
            title = EXCLUDED.title,
            status = EXCLUDED.status,
            state_json = EXCLUDED.state_json,
            version = EXCLUDED.version,
            linked_offer_letter_id = EXCLUDED.linked_offer_letter_id,
            updated_at = EXCLUDED.updated_at
        """
    )

    op.execute(
        "ALTER TABLE mw_threads ALTER COLUMN title SET DEFAULT 'Untitled Chat'"
    )

    op.execute(
        """
        UPDATE mw_threads
        SET title = 'Untitled Chat'
        WHERE title = 'Untitled Offer Letter'
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_elements_thread_id")
    op.execute("DROP INDEX IF EXISTS idx_mw_elements_created_by")
    op.execute("DROP INDEX IF EXISTS idx_mw_elements_company_status")
    op.execute("DROP TABLE IF EXISTS mw_elements")
    op.execute(
        "ALTER TABLE mw_threads ALTER COLUMN title SET DEFAULT 'Untitled Offer Letter'"
    )
