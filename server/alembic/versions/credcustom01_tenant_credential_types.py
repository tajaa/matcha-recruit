"""Add tenant-owned custom credential types.

Revision ID: credcustom01
Revises: credvis01
"""

from alembic import op


revision = "credcustom01"
down_revision = "credvis01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE credential_types
        ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
        ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_credential_types_company
        ON credential_types(company_id)
        WHERE company_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_credential_types_company_label
        ON credential_types(company_id, lower(btrim(label)))
        WHERE company_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_credential_types_company_label")
    op.execute("DROP INDEX IF EXISTS idx_credential_types_company")
    op.execute("ALTER TABLE credential_types DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE credential_types DROP COLUMN IF EXISTS company_id")
