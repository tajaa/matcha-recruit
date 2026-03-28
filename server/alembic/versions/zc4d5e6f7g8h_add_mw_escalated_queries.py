"""add mw_escalated_queries table for low-confidence human loop

Revision ID: zc4d5e6f7g8h
Revises: zb3c4d5e6f7g
Create Date: 2026-03-27
"""

from alembic import op

revision = "zc4d5e6f7g8h"
down_revision = "zb3c4d5e6f7g"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_escalated_queries (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            thread_id        UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
            message_id       UUID NOT NULL REFERENCES mw_messages(id) ON DELETE CASCADE,
            user_message_id  UUID REFERENCES mw_messages(id) ON DELETE SET NULL,
            status           VARCHAR(20) NOT NULL DEFAULT 'open'
                               CHECK (status IN ('open','in_review','resolved','dismissed')),
            severity         VARCHAR(20) NOT NULL DEFAULT 'medium'
                               CHECK (severity IN ('high','medium','low')),
            title            TEXT NOT NULL,
            user_query       TEXT NOT NULL,
            ai_reply         TEXT,
            ai_mode          VARCHAR(20),
            ai_confidence    FLOAT,
            missing_fields   JSONB,
            resolution_note  TEXT,
            resolved_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            resolved_at      TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_mw_escalated_company_status
            ON mw_escalated_queries(company_id, status);
        CREATE INDEX IF NOT EXISTS idx_mw_escalated_thread
            ON mw_escalated_queries(thread_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_escalated_queries")
