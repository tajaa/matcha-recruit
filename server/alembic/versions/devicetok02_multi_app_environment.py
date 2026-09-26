"""Store APNs environment for Matcha Schedule and Werk devices.

Revision ID: devicetok02
Revises: mobsess02
"""

from alembic import op


revision = "devicetok02"
down_revision = "mobsess02"
branch_labels = None
depends_on = "devicetok01"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE device_tokens
        ADD COLUMN environment VARCHAR(12)
        CHECK (environment IN ('sandbox', 'production'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE device_tokens DROP COLUMN environment")
