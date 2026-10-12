"""Allow separate private Espresso conversations without losing existing history.

Revision ID: assistthread01
Revises: zzzzcappe47

The canonical conversation still has a unique company/slug, so old clients
can keep opening it. Ownership and private visibility constraints stay intact.
Downgrade refuses when multiple conversations exist rather than deleting mail
or merging independent histories. Archive/export/remove extra conversations
explicitly before retrying a rollback. Apply before deploying the API.
"""
from alembic import op

revision = "assistthread01"
down_revision = "zzzzcappe47"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE INDEX IF NOT EXISTS ix_channels_assistant_conversations
        ON channels(company_id, assistant_user_id, updated_at DESC, id DESC)
        WHERE channel_scope = 'assistant'""")
    op.execute("DROP INDEX IF EXISTS uq_channels_assistant_user")


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM channels WHERE channel_scope = 'assistant'
                   GROUP BY company_id, assistant_user_id HAVING COUNT(*) > 1) THEN
            RAISE EXCEPTION 'Multiple Espresso conversations exist; rollback requires explicit data reconciliation';
        END IF;
    END $$""")
    op.execute("""CREATE UNIQUE INDEX uq_channels_assistant_user
        ON channels(company_id, assistant_user_id) WHERE channel_scope = 'assistant'""")
    op.execute("DROP INDEX IF EXISTS ix_channels_assistant_conversations")
