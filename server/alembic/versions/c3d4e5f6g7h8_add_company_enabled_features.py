"""add company enabled_features

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-28 00:00:00.000000

"""
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6g7h8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None

ALL_FEATURES = {
    "offer_letters": True,
    "policies": True,
    "compliance": True,
    "employees": True,
    "vibe_checks": True,
    "enps": True,
    "performance_reviews": True,
    "er_copilot": True,
    "incidents": True,
    "time_off": True,
}


def upgrade() -> None:
    op.add_column(
        'companies',
        sa.Column(
            'enabled_features',
            JSONB,
            server_default=sa.text("'{\"offer_letters\": true}'::jsonb"),
            nullable=True,
        )
    )

    # Backfill: approved companies get ALL features so nothing breaks
    op.execute(
        sa.text(
            "UPDATE companies SET enabled_features = :features "
            "WHERE status = 'approved' OR status IS NULL"
        ).bindparams(features=json.dumps(ALL_FEATURES))
    )


def downgrade() -> None:
    op.drop_column('companies', 'enabled_features')
