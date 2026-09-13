"""Track whether a business-location timezone is automatic or manually set."""

from alembic import op


revision = "empsched24"
down_revision = "empsched23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE business_locations
        ADD COLUMN timezone_source VARCHAR(10) NOT NULL DEFAULT 'manual'
            CHECK (timezone_source IN ('auto', 'manual'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE business_locations DROP COLUMN timezone_source")
