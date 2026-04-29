"""Add signup_source + ir_onboarding_completed_at to companies.

signup_source disambiguates self-serve IR-only signups from sales-led
bespoke customers when feature flags alone are insufficient (e.g., a
partially-provisioned bespoke customer with only `incidents` enabled
shouldn't fall into the slim IR layout).

ir_onboarding_completed_at lets the IR-only onboarding wizard track
completion without an extra table.

Revision ID: zzzf2g3h4i5j6
Revises: zzze1f2g3h4i5
Create Date: 2026-04-29
"""
from alembic import op

revision = "zzzf2g3h4i5j6"
down_revision = "zzze1f2g3h4i5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS signup_source VARCHAR(32)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS ir_onboarding_completed_at TIMESTAMPTZ")
    op.execute("UPDATE companies SET signup_source = 'bespoke' WHERE signup_source IS NULL")


def downgrade():
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS ir_onboarding_completed_at")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS signup_source")
