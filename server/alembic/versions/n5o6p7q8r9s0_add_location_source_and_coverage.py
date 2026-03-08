"""Add source/coverage_status to business_locations + jurisdiction_coverage_requests table

Adds source tracking and coverage status columns to business_locations for the
auto-derive-jurisdictions-from-employees feature. Creates the
jurisdiction_coverage_requests table for admin queue of unknown jurisdictions.

Revision ID: n5o6p7q8r9s0
Revises: o0p1q2r3s4t5
Create Date: 2026-03-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, None] = "o0p1q2r3s4t5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- business_locations: source tracking + coverage status ---
    op.execute(
        "ALTER TABLE business_locations "
        "ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual'"
    )
    op.execute(
        "ALTER TABLE business_locations "
        "ADD COLUMN IF NOT EXISTS coverage_status VARCHAR(20) DEFAULT 'covered'"
    )

    # Backfill existing rows
    op.execute(
        "UPDATE business_locations SET source = 'manual' WHERE source IS NULL"
    )
    op.execute(
        "UPDATE business_locations SET coverage_status = 'covered' WHERE coverage_status IS NULL"
    )

    # --- employees: add work_zip column ---
    op.execute(
        "ALTER TABLE employees "
        "ADD COLUMN IF NOT EXISTS work_zip VARCHAR(10)"
    )

    # Prevent duplicate locations for same city+state within a company
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bl_company_city_state "
        "ON business_locations (company_id, LOWER(city), UPPER(state))"
    )

    # --- jurisdiction_coverage_requests table ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS jurisdiction_coverage_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            city VARCHAR(100) NOT NULL,
            state VARCHAR(2) NOT NULL,
            county VARCHAR(100),
            requested_by_company_id UUID NOT NULL REFERENCES companies(id),
            location_id UUID REFERENCES business_locations(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'in_progress', 'completed', 'dismissed')),
            admin_notes TEXT,
            processed_by UUID REFERENCES users(id),
            processed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(city, state)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jcr_status "
        "ON jurisdiction_coverage_requests(status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jcr_status")
    op.execute("DROP TABLE IF EXISTS jurisdiction_coverage_requests")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS work_zip")
    op.execute("DROP INDEX IF EXISTS idx_bl_company_city_state")
    op.execute(
        "ALTER TABLE business_locations DROP COLUMN IF EXISTS coverage_status"
    )
    op.execute(
        "ALTER TABLE business_locations DROP COLUMN IF EXISTS source"
    )
