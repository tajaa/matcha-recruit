"""Driver-risk scoring fields on mvr_reviews (generalize MVR off healthcare)

Revision ID: driverrisk01
Revises: lossdev01
Create Date: 2026-06-22

Gap-analysis #15 — lift MVR tracking out of the healthcare-only resident_care
vertical into a standalone driver-risk surface for any employer with drivers
(commercial-auto entry point), and add the inputs needed to SCORE a driver
(clean / marginal / high-risk) rather than just track review currency.

Reuses (does not duplicate) the existing mvr_reviews table — adds the scoring
columns. resident_care keeps reading the same table; the new driver_risk feature
adds the scored fleet view + insurer PDF on top.
"""

from alembic import op


revision = "driverrisk01"
down_revision = "lossdev01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE mvr_reviews ADD COLUMN IF NOT EXISTS violation_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE mvr_reviews ADD COLUMN IF NOT EXISTS accident_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE mvr_reviews ADD COLUMN IF NOT EXISTS major_violation BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(
        "ALTER TABLE mvr_reviews ADD COLUMN IF NOT EXISTS license_status VARCHAR(12) NOT NULL DEFAULT 'valid'"
    )
    # widen review_type beyond hire/annual (post-incident etc.) — drop the old CHECK
    op.execute("ALTER TABLE mvr_reviews DROP CONSTRAINT IF EXISTS mvr_reviews_review_type_check")
    op.execute(
        "ALTER TABLE mvr_reviews ADD CONSTRAINT mvr_reviews_review_type_check "
        "CHECK (review_type IN ('hire','annual','post_incident','periodic'))"
    )
    op.execute(
        "ALTER TABLE mvr_reviews ADD CONSTRAINT mvr_reviews_license_status_check "
        "CHECK (license_status IN ('valid','suspended','expired','unknown'))"
    )


def downgrade():
    op.execute("ALTER TABLE mvr_reviews DROP CONSTRAINT IF EXISTS mvr_reviews_license_status_check")
    op.execute("ALTER TABLE mvr_reviews DROP COLUMN IF EXISTS license_status")
    op.execute("ALTER TABLE mvr_reviews DROP COLUMN IF EXISTS major_violation")
    op.execute("ALTER TABLE mvr_reviews DROP COLUMN IF EXISTS accident_count")
    op.execute("ALTER TABLE mvr_reviews DROP COLUMN IF EXISTS violation_count")
