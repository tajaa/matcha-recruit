"""Prop draft tickets + their repo-grounded chat

A "Prop" is a draft ticket of kind feat|fix where a collaborator chats with an
AI grounded on an element's code snapshot to shape the idea, then promotes it to
a real kanban ticket. No drafts system existed before (generate_task_draft was
ephemeral). Chat messages mirror ir_incident_ai_messages.

Revision ID: propdraft0002
Revises: propsnap0001
Create Date: 2026-06-02
"""

from alembic import op


revision = "propdraft0002"
down_revision = "propsnap0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_ticket_drafts (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id       UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            company_id       UUID NOT NULL,
            element_id       TEXT REFERENCES mw_project_elements(id) ON DELETE SET NULL,
            kind             TEXT NOT NULL DEFAULT 'feat' CHECK (kind IN ('feat', 'fix')),
            title            TEXT,
            description      TEXT,
            draft_subtasks   JSONB NOT NULL DEFAULT '[]'::jsonb,
            priority         TEXT NOT NULL DEFAULT 'medium',
            status           TEXT NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft', 'promoted', 'discarded')),
            promoted_task_id UUID REFERENCES mw_tasks(id) ON DELETE SET NULL,
            created_by       UUID,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_ticket_drafts_project_status
            ON mw_ticket_drafts (project_id, status)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_ticket_draft_messages (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            draft_id    UUID NOT NULL REFERENCES mw_ticket_drafts(id) ON DELETE CASCADE,
            project_id  UUID NOT NULL,
            role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content     TEXT NOT NULL,
            metadata    JSONB,
            created_by  UUID,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_ticket_draft_messages_draft
            ON mw_ticket_draft_messages (draft_id, created_at)
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_ticket_draft_messages")
    op.execute("DROP TABLE IF EXISTS mw_ticket_drafts")
