"""add_gumfit_assets_table

Revision ID: f66269e69a70
Revises: 7c3a7b1e830a
Create Date: 2026-01-21 14:12:36.760542

"""
from typing import Sequence, Union

from alembic import op

revision = 'f66269e69a70'
down_revision = '7c3a7b1e830a'
branch_labels = None
depends_on = None
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'f66269e69a70'
down_revision: Union[str, Sequence[str], None] = '7c3a7b1e830a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create gumfit_assets table for marketing/landing page images."""
    op.create_table(
        'gumfit_assets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('category', sa.String(50), nullable=False, server_default='general'),
        sa.Column('file_type', sa.String(50), nullable=True),
        sa.Column('file_size', sa.Integer, nullable=True),
        sa.Column('width', sa.Integer, nullable=True),
        sa.Column('height', sa.Integer, nullable=True),
        sa.Column('alt_text', sa.String(500), nullable=True),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )

    # Index for category filtering
    op.create_index('ix_gumfit_assets_category', 'gumfit_assets', ['category'])

    # Index for listing by upload date
    op.create_index('ix_gumfit_assets_created_at', 'gumfit_assets', ['created_at'])


def downgrade() -> None:
    """Drop gumfit_assets table."""
    op.drop_index('ix_gumfit_assets_created_at', table_name='gumfit_assets')
    op.drop_index('ix_gumfit_assets_category', table_name='gumfit_assets')
    op.drop_table('gumfit_assets')
