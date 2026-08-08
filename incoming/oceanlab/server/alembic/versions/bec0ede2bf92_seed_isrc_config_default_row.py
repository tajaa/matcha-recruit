"""seed isrc config default row

Revision ID: bec0ede2bf92
Revises: 294504605e28
Create Date: 2026-08-07 13:13:07.595599

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

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
    # ON CONFLICT DO NOTHING so this is safe to run against a DB that
    # already has the row (e.g. seeded via scripts/seed.py or the old
    # create-on-read GET path).
    op.execute(
        sa.text(
            "INSERT INTO isrc_config (id, registrant_prefix, year_digits, next_designation) "
            "VALUES (1, '', '', 1) ON CONFLICT (id) DO NOTHING"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Only remove the pristine default row — never destroy real config.
    op.execute(
        isrc_config.delete().where(
            sa.and_(isrc_config.c.id == 1, isrc_config.c.registrant_prefix == "")
        )
    )
