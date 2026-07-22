"""cappe: persisted Merlin conversations

Merlin (AI chat page editing, `services/merlin.py`) has been stateless since it
shipped — the transcript lived in the browser's localStorage, so it was lost on
a device change and could never be resumed. These two tables move it server-side
and allow MULTIPLE named conversations per page (the panel gets a history list).

`steps` and `attachments` are written by later phases (the agent tool-loop trace
and chat image uploads); they're created here so the message table isn't
re-migrated for each one.

Additive: no existing table is touched. Cascades follow the account → site →
page chain that already exists, so deleting a page takes its conversations with
it.

Revision ID: zzzzcappe22
Revises: zzzzcappe21
Create Date: 2026-07-22
"""
from alembic import op

revision = "zzzzcappe22"
down_revision = "zzzzcappe21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_merlin_conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            page_id UUID NOT NULL REFERENCES cappe_pages(id) ON DELETE CASCADE,
            title VARCHAR(120) NOT NULL DEFAULT 'New conversation',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # The panel lists a page's conversations most-recently-used first.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_merlin_convos_page "
        "ON cappe_merlin_conversations(page_id, updated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_merlin_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES cappe_merlin_conversations(id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL DEFAULT '',
            results JSONB,
            steps JSONB,
            attachments JSONB,
            tier VARCHAR(16),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_merlin_msgs_convo "
        "ON cappe_merlin_messages(conversation_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_merlin_messages")
    op.execute("DROP TABLE IF EXISTS cappe_merlin_conversations")
