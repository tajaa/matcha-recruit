"""Sales campaign playbooks: consulting outreach.

A campaign can run the consulting playbook (`playbook = 'consulting'`) with
one booking link (`cta_url`) every message asks for. Each prospect then
carries why it is worth writing to now: its segment, the service that fits,
the public signal (one sentence, backed by the prospect's sources) and a fit
of 1-3. Adds columns only; existing rows keep empty defaults and behave as
before.

Revision ID: mwsales03
Revises: mwjobs05
"""

from alembic import op

revision = "mwsales03"
down_revision = "mwjobs05"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """ALTER TABLE mw_sales_campaigns
            ADD COLUMN playbook TEXT NOT NULL DEFAULT '',
            ADD COLUMN cta_url TEXT NOT NULL DEFAULT ''"""
    )
    op.execute(
        "ALTER TABLE mw_sales_campaigns ADD CONSTRAINT mw_sales_campaigns_playbook_check "
        "CHECK (playbook IN ('', 'consulting')) NOT VALID"
    )
    op.execute("ALTER TABLE mw_sales_campaigns VALIDATE CONSTRAINT mw_sales_campaigns_playbook_check")
    op.execute(
        """ALTER TABLE mw_sales_prospects
            ADD COLUMN segment TEXT NOT NULL DEFAULT '',
            ADD COLUMN service TEXT NOT NULL DEFAULT '',
            ADD COLUMN signal TEXT NOT NULL DEFAULT '',
            ADD COLUMN fit SMALLINT"""
    )
    op.execute(
        "ALTER TABLE mw_sales_prospects ADD CONSTRAINT mw_sales_prospects_fit_check "
        "CHECK (fit IS NULL OR fit BETWEEN 1 AND 3) NOT VALID"
    )
    op.execute("ALTER TABLE mw_sales_prospects VALIDATE CONSTRAINT mw_sales_prospects_fit_check")


def downgrade():
    op.execute(
        """ALTER TABLE mw_sales_prospects
            DROP CONSTRAINT IF EXISTS mw_sales_prospects_fit_check,
            DROP COLUMN fit, DROP COLUMN signal, DROP COLUMN service, DROP COLUMN segment"""
    )
    op.execute(
        """ALTER TABLE mw_sales_campaigns
            DROP CONSTRAINT IF EXISTS mw_sales_campaigns_playbook_check,
            DROP COLUMN cta_url, DROP COLUMN playbook"""
    )
