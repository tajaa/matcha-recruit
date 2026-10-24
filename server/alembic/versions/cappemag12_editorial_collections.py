"""Creator-owned editorial design collections.

Revision ID: cappemag12
Revises: cappemag11
Create Date: 2026-10-23
"""
from alembic import op

revision = "cappemag12"
down_revision = "cappemag11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE cappe_studio_collections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            name VARCHAR(80) NOT NULL CHECK (length(btrim(name)) > 0),
            doc JSONB NOT NULL CHECK (jsonb_typeof(doc) = 'object'),
            page_count INTEGER NOT NULL CHECK (page_count BETWEEN 1 AND 32),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_cappe_studio_collections_account "
               "ON cappe_studio_collections (account_id, created_at DESC, id)")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM cappe_studio_collections) THEN
                RAISE EXCEPTION 'Saved editorial collections exist; export or remove them before downgrading';
            END IF;
        END $$
    """)
    op.execute("DROP TABLE cappe_studio_collections")
