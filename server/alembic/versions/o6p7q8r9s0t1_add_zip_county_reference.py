"""add zip_county_reference table for zip-to-county lookups

Revision ID: o6p7q8r9s0t1
Revises: n5o6p7q8r9s0
Create Date: 2026-03-08
"""

from alembic import op


revision = "o6p7q8r9s0t1"
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS zip_county_reference (
            zipcode VARCHAR(5) PRIMARY KEY,
            county VARCHAR(100) NOT NULL,
            state VARCHAR(2) NOT NULL,
            city VARCHAR(100)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_zcr_state ON zip_county_reference(state)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_zcr_state")
    op.execute("DROP TABLE IF EXISTS zip_county_reference")
