"""Add jurisdiction_sources table for dynamic context learning

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6g7h8i9j0k1'
down_revision: Union[str, None] = 'e5f6g7h8i9j0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create jurisdiction_sources table
    op.create_table(
        'jurisdiction_sources',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('jurisdiction_id', postgresql.UUID(), nullable=False),
        sa.Column('domain', sa.Text(), nullable=False),
        sa.Column('source_name', sa.Text(), nullable=True),
        sa.Column('categories', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('success_count', sa.Integer(), server_default='1', nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['jurisdiction_id'], ['jurisdictions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('jurisdiction_id', 'domain', name='uq_jurisdiction_sources_jurisdiction_domain'),
    )

    # Create indexes
    op.create_index('idx_jurisdiction_sources_jurisdiction_id', 'jurisdiction_sources', ['jurisdiction_id'])
    op.create_index('idx_jurisdiction_sources_domain', 'jurisdiction_sources', ['domain'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_jurisdiction_sources_domain', table_name='jurisdiction_sources')
    op.drop_index('idx_jurisdiction_sources_jurisdiction_id', table_name='jurisdiction_sources')

    # Drop table
    op.drop_table('jurisdiction_sources')
