"""merge elementrepo + hris heads

Revision ID: 53df72e778a4
Revises: elementrepo0001, emphris0001
Create Date: 2026-05-24 23:31:59.655175

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53df72e778a4'
down_revision: Union[str, Sequence[str], None] = ('elementrepo0001', 'emphris0001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
