"""per-establishment OSHA: EIN/NAICS identity + location-scoped 300A summaries

Revision ID: osha300a01
Revises: mwicon0001
Create Date: 2026-05-27

Adds the employer/establishment identity columns OSHA 300A + ITA filing need
(EIN, NAICS, legal name, address) and makes osha_annual_summaries
per-establishment instead of company-wide.

Notes:
- companies.address also closes a latent bug: ir_incidents/osha.py's 301 form
  query selects `c.address`, which did not exist before this revision (the
  endpoint 500'd with UndefinedColumnError on every call).
- The old UNIQUE(company_id, year) is replaced with a NULL-safe unique index
  keyed on COALESCE(location_id, <sentinel>) so the per-establishment upsert can
  target it via ON CONFLICT. A bare UNIQUE(company_id, location_id, year) would
  treat NULL location_id rows as distinct (Postgres NULL semantics) and silently
  permit duplicates.
- No backfill: pre-existing summary rows keep location_id = NULL (a legacy
  whole-company bucket). The new endpoints always write a non-null location_id
  and filter on it, so legacy rows are never read by the new code path. We
  cannot infer which establishment a legacy company-wide aggregate belonged to.
"""

from alembic import op


revision = "osha300a01"
down_revision = "mwicon0001"
branch_labels = None
depends_on = None

_SENTINEL = "00000000-0000-0000-0000-000000000000"


def upgrade():
    # companies — employer-level identity (+ address bug fix)
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS legal_name VARCHAR(255)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS ein VARCHAR(20)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS naics VARCHAR(10)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS address VARCHAR(500)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS zip VARCHAR(10)")

    # business_locations — per-establishment identity + headcount for ITA
    op.execute("ALTER TABLE business_locations ADD COLUMN IF NOT EXISTS ein VARCHAR(20)")
    op.execute("ALTER TABLE business_locations ADD COLUMN IF NOT EXISTS naics VARCHAR(10)")
    op.execute("ALTER TABLE business_locations ADD COLUMN IF NOT EXISTS max_employees INTEGER")
    op.execute("ALTER TABLE business_locations ADD COLUMN IF NOT EXISTS annual_avg_employees INTEGER")

    # osha_annual_summaries — per-establishment
    op.execute(
        "ALTER TABLE osha_annual_summaries ADD COLUMN IF NOT EXISTS location_id UUID "
        "REFERENCES business_locations(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE osha_annual_summaries DROP CONSTRAINT IF EXISTS osha_annual_summaries_company_id_year_key")
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_osha_summaries_company_loc_year
          ON osha_annual_summaries
          (company_id, COALESCE(location_id, '{_SENTINEL}'::uuid), year)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_osha_summaries_company_loc_year")
    op.execute(
        "ALTER TABLE osha_annual_summaries "
        "ADD CONSTRAINT osha_annual_summaries_company_id_year_key UNIQUE (company_id, year)"
    )
    op.execute("ALTER TABLE osha_annual_summaries DROP COLUMN IF EXISTS location_id")

    op.execute("ALTER TABLE business_locations DROP COLUMN IF EXISTS annual_avg_employees")
    op.execute("ALTER TABLE business_locations DROP COLUMN IF EXISTS max_employees")
    op.execute("ALTER TABLE business_locations DROP COLUMN IF EXISTS naics")
    op.execute("ALTER TABLE business_locations DROP COLUMN IF EXISTS ein")

    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS zip")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS address")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS naics")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS ein")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS legal_name")
