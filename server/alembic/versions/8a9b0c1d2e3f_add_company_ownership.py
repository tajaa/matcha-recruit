"""add_company_ownership

Revision ID: 8a9b0c1d2e3f
Revises: f66269e69a70
Create Date: 2026-01-25 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a9b0c1d2e3f'
down_revision: Union[str, Sequence[str], None] = 'f66269e69a70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add owner_id to companies table to track who created the company."""
    # Add owner_id column (nullable initially to handle existing data)
    op.add_column('companies', sa.Column('owner_id', sa.UUID(), nullable=True))

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_companies_owner',
        'companies',
        'users',
        ['owner_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add index for performance
    op.create_index('idx_companies_owner', 'companies', ['owner_id'])


def downgrade() -> None:
    """Remove company ownership tracking."""
    op.drop_index('idx_companies_owner', table_name='companies')
    op.drop_constraint('fk_companies_owner', 'companies', type_='foreignkey')
    op.drop_column('companies', 'owner_id')
