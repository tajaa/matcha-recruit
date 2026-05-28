"""Add company OSHA executive identity (300A cert block: name, title, phone).

The OSHA 300A faithful PDF cert block ("Sign here. … Company executive · Title ·
Phone · Date") needs an identity for the signing executive. These are stable
company-level defaults — typed once on Company Settings → "OSHA / ITA Filing
Identity" — so every per-establishment 300A PDF for a given year prints with the
same signer block. Per-year certified_date stays on osha_annual_summaries
(when this particular year's summary was signed).

Idempotent (`ADD COLUMN IF NOT EXISTS`) so re-running against a partially-
upgraded database is safe.

Revision ID: oshaexec01
Revises: brokerrisk01
Create Date: 2026-05-27
"""
from alembic import op


revision = "oshaexec01"
down_revision = "brokerrisk01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS executive_name VARCHAR(255)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS executive_title VARCHAR(255)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS executive_phone VARCHAR(64)")


def downgrade():
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS executive_phone")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS executive_title")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS executive_name")
