"""Add companies.is_test — first-class designation for demo/buyer-demo
tenants (Sunset Smile Dental Group, 720 Behavioral, Onc).

Backs the bidirectional dev<->prod test-tenant sync (scripts/sync_tenants.py):
the sync engine reads `SELECT id FROM companies WHERE is_test` on both sides
instead of a hardcoded name allowlist, so a newly-flagged tenant is picked up
automatically at the next sync run with no script edit.

Revision ID: testacct01
Revises: schedrules01
Create Date: 2026-07-24
"""
from alembic import op

revision = "testacct01"
down_revision = "schedrules01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        UPDATE companies SET is_test = true WHERE id IN (
          '287fffb5-ea50-40a2-bf07-6b5c2ca3c400',  -- Sunset Smile Dental Group
          '1a1123e5-4c24-4735-8501-9a64a1dd7691',  -- 720 Behavioral
          '06f8018c-9827-4c05-9d33-15a3db8ee082'   -- Onc
        )
    """)


def downgrade():
    op.execute("""
        ALTER TABLE companies DROP COLUMN IF EXISTS is_test
    """)
