"""Sales opt-out: per-sender suppression list, campaign footer, opted_out status.

Revision ID: mwsales02
Revises: mwsales01
"""

from alembic import op

revision = "mwsales02"
down_revision = "mwsales01"
branch_labels = None
depends_on = None

_STATUSES = "'prospect','draft','approved','claimed','sent','failed','unknown'"


def upgrade():
    # One do-not-contact list per sender, shared by every campaign they run.
    op.execute("""
        CREATE TABLE mw_sales_suppressions (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, email)
        )
    """)
    op.execute(
        "ALTER TABLE mw_sales_campaigns ADD COLUMN footer TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE mw_sales_prospects DROP CONSTRAINT mw_sales_prospects_status_check"
    )
    op.execute(
        "ALTER TABLE mw_sales_prospects ADD CONSTRAINT mw_sales_prospects_status_check "
        f"CHECK (status IN ({_STATUSES},'opted_out'))"
    )


def downgrade():
    op.execute(
        "UPDATE mw_sales_prospects SET status = 'prospect' WHERE status = 'opted_out'"
    )
    op.execute(
        "ALTER TABLE mw_sales_prospects DROP CONSTRAINT mw_sales_prospects_status_check"
    )
    op.execute(
        "ALTER TABLE mw_sales_prospects ADD CONSTRAINT mw_sales_prospects_status_check "
        f"CHECK (status IN ({_STATUSES}))"
    )
    op.execute("ALTER TABLE mw_sales_campaigns DROP COLUMN footer")
    op.execute("DROP TABLE mw_sales_suppressions")
