"""broker book of business: per-client renewal date

The broker's own renewal date for a linked client. Nothing on
broker_company_links carried a policy term before this — only lifecycle dates
(linked_at / activated_at / terminated_at / grace_until). Nullable: unset rows
fall back at read time to MIN(company_coverage_lines.expiry_date), and render
"—" when that is empty too.

Revision ID: brokerrenew01
Revises: empsched04
Create Date: 2026-08-18
"""

from alembic import op

revision = "brokerrenew01"
down_revision = "empsched04"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE broker_company_links ADD COLUMN IF NOT EXISTS renewal_date DATE")


def downgrade():
    op.execute("ALTER TABLE broker_company_links DROP COLUMN IF EXISTS renewal_date")
