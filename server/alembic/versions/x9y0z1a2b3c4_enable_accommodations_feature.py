"""enable accommodations feature in platform_settings and default company features

Revision ID: x9y0z1a2b3c4
Revises: w8x9y0z1a2b3
Create Date: 2026-03-26
"""

from alembic import op


revision = "x9y0z1a2b3c4"
down_revision = "w8x9y0z1a2b3"
branch_labels = None
depends_on = None


def upgrade():
    # Add accommodations to platform visible_features if not already present
    op.execute(
        """
        UPDATE platform_settings
        SET value = CASE
            WHEN value @> '"accommodations"'
            THEN value
            ELSE value || '["accommodations"]'::jsonb
        END
        WHERE key = 'visible_features'
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE platform_settings
        SET value = value - 'accommodations'
        WHERE key = 'visible_features'
        """
    )
