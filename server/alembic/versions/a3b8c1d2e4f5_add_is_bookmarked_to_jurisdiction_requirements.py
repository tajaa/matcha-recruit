"""add is_bookmarked to jurisdiction_requirements

Revision ID: a3b8c1d2e4f5
Revises: e6714d5d523f
Create Date: 2026-03-03 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b8c1d2e4f5'
down_revision: Union[str, Sequence[str], None] = 'e6714d5d523f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'jurisdiction_requirements',
        sa.Column('is_bookmarked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('jurisdiction_requirements', 'is_bookmarked')
