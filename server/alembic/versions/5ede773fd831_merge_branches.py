"""merge_branches

Revision ID: 5ede773fd831
Revises: b1c2d3e4f5a7, j1k2l3m4n5o6, m4n5o6p7q8r9, p7q8r9s0t1u2, q1r2s3t4u5v6
Create Date: 2026-03-01 20:53:52.375043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ede773fd831'
down_revision: Union[str, Sequence[str], None] = ('b1c2d3e4f5a7', 'j1k2l3m4n5o6', 'm4n5o6p7q8r9', 'p7q8r9s0t1u2', 'q1r2s3t4u5v6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
