"""Widen mvr_reviews.review_type past VARCHAR(10)

Revision ID: mvrtype01
Revises: citeverify01
Create Date: 2026-07-11

driverrisk01 widened the review_type CHECK constraint to allow
'post_incident' and 'periodic', but left the column at VARCHAR(10) (the
original rescare01 width, sized for 'hire'/'annual'). 'post_incident' is
13 characters, so any create/update with that advertised review type raised
StringDataRightTruncationError → 500. Widen the column to VARCHAR(20) so all
four documented review types are storable.

Idempotent: ALTER COLUMN ... TYPE to a wider varchar is a no-op if already
applied and never truncates existing data.
"""

from alembic import op


revision = "mvrtype01"
down_revision = "citeverify01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE mvr_reviews ALTER COLUMN review_type TYPE VARCHAR(20)")


def downgrade():
    # No-op: narrowing back to VARCHAR(10) would truncate 'post_incident'
    # rows. Intentionally left as a widening-only migration.
    pass
