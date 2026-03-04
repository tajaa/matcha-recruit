"""add sort_order to jurisdiction_requirements

Revision ID: b4c5d6e7f8a9
Revises: a3b8c1d2e4f5
Create Date: 2026-03-03 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = 'a3b8c1d2e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'jurisdiction_requirements',
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
    )


def downgrade() -> None:
    op.drop_column('jurisdiction_requirements', 'sort_order')
