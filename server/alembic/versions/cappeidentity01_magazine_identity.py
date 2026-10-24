"""Private, versioned magazine identities for Gummfit Studio.

Revision ID: cappeidentity01
Revises: cappemag11
Create Date: 2026-10-23
"""
from alembic import op

revision = "cappeidentity01"
down_revision = "cappemag11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE cappe_studio_identities (
            site_id UUID PRIMARY KEY REFERENCES cappe_sites(id) ON DELETE CASCADE,
            rev BIGINT NOT NULL CHECK (rev > 0),
            identity JSONB NOT NULL CHECK (jsonb_typeof(identity) = 'object'),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM cappe_studio_identities) THEN
                RAISE EXCEPTION 'Saved magazine identities exist; export or remove them before downgrading';
            END IF;
        END $$
    """)
    op.execute("DROP TABLE cappe_studio_identities")
