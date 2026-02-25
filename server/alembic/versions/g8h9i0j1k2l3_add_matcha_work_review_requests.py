"""add matcha work review requests

Revision ID: g8h9i0j1k2l3
Revises: f9a0b1c2d3e4
Create Date: 2026-02-25
"""

from alembic import op


revision = "g8h9i0j1k2l3"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_review_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            recipient_email VARCHAR(320) NOT NULL,
            token VARCHAR(255) NOT NULL UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sent', 'failed', 'submitted')),
            feedback TEXT,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            sent_at TIMESTAMPTZ,
            submitted_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(thread_id, recipient_email)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_review_requests_thread_id
        ON mw_review_requests(thread_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_review_requests_company_status
        ON mw_review_requests(company_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_review_requests_token
        ON mw_review_requests(token)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_review_requests_token")
    op.execute("DROP INDEX IF EXISTS idx_mw_review_requests_company_status")
    op.execute("DROP INDEX IF EXISTS idx_mw_review_requests_thread_id")
    op.execute("DROP TABLE IF EXISTS mw_review_requests")
