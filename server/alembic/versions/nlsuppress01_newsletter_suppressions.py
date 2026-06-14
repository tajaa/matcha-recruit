"""Newsletter suppression list — make subscriber deletes survive re-sync.

`sync_platform_users()` runs on every GET /subscribers and re-inserts every
active platform user as a subscriber (ON CONFLICT (email) DO NOTHING). A GDPR
hard-delete therefore resurrected on the next list fetch for any platform-user
email. This table records removed emails so the sync skips them; the delete
stays a hard delete (PII erased from newsletter_subscribers).

Revision ID: nlsuppress01
Revises: zzzzcappe12
"""
from alembic import op

revision = "nlsuppress01"
down_revision = "zzzzcappe12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS newsletter_suppressions (
            email VARCHAR(255) PRIMARY KEY,
            reason VARCHAR(50) DEFAULT 'admin_delete',
            suppressed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            suppressed_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS newsletter_suppressions")
