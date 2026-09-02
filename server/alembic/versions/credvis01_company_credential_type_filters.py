"""Add tenant-scoped credential type dropdown filters.

Revision ID: credvis01
Revises: empsched19
"""

from alembic import op


revision = "credvis01"
down_revision = "empsched19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The presence of a settings row means the company has configured a
    # filter. Its absence preserves the legacy behavior of showing every type.
    # Keeping the selected values in a child table gives every type a real FK
    # while still allowing a deliberately empty selection.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_credential_type_filters (
            company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_credential_type_filter_items (
            company_id UUID NOT NULL REFERENCES company_credential_type_filters(company_id) ON DELETE CASCADE,
            credential_type_id UUID NOT NULL REFERENCES credential_types(id) ON DELETE CASCADE,
            PRIMARY KEY (company_id, credential_type_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_company_credential_type_filter_items_type
        ON company_credential_type_filter_items(credential_type_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_credential_type_filter_items")
    op.execute("DROP TABLE IF EXISTS company_credential_type_filters")
