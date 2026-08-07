"""seed isrc config default row

Revision ID: bec0ede2bf92
Revises: 294504605e28
Create Date: 2026-08-07 13:13:07.595599

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bec0ede2bf92'
down_revision: Union[str, Sequence[str], None] = '294504605e28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


isrc_config = sa.table(
    "isrc_config",
    sa.column("id", sa.Integer),
    sa.column("registrant_prefix", sa.String),
    sa.column("year_digits", sa.String),
    sa.column("next_designation", sa.Integer),
)


def upgrade() -> None:
    """Upgrade schema."""
    # Guarantee the id=1 row exists so app code (GET /settings/isrc, the
    # assign_isrc FOR UPDATE lock target) never has to create-on-read.
    op.execute(
        isrc_config.insert().values(
            id=1, registrant_prefix="", year_digits="", next_designation=1
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(isrc_config.delete().where(isrc_config.c.id == 1))
