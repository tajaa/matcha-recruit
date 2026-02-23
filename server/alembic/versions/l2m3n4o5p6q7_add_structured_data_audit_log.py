"""Add structured data audit log table

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op

revision = 'l2m3n4o5p6q7'
down_revision = 'k1l2m3n4o5p6'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l2m3n4o5p6q7'
down_revision: Union[str, None] = 'k1l2m3n4o5p6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Audit log for Tier 1 structured data operations
    op.execute("""
        CREATE TABLE IF NOT EXISTS structured_data_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ DEFAULT NOW(),

            -- What happened
            event_type VARCHAR(50) NOT NULL,

            -- Context
            source_id UUID REFERENCES structured_data_sources(id) ON DELETE SET NULL,
            jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE SET NULL,
            cache_id UUID REFERENCES structured_data_cache(id) ON DELETE SET NULL,

            -- Details
            details JSONB,

            -- Traceability
            triggered_by VARCHAR(100)
        )
    """)

    # Indexes for common queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sda_created_at
        ON structured_data_audit_log(created_at)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sda_source_id
        ON structured_data_audit_log(source_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sda_event_type
        ON structured_data_audit_log(event_type)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sda_jurisdiction_id
        ON structured_data_audit_log(jurisdiction_id)
    """)

    # Add verification columns to structured_data_cache for Phase 3
    op.execute("""
        ALTER TABLE structured_data_cache
        ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ
    """)

    op.execute("""
        ALTER TABLE structured_data_cache
        ADD COLUMN IF NOT EXISTS verification_status VARCHAR(20) DEFAULT 'pending'
    """)

    op.execute("""
        ALTER TABLE structured_data_cache
        ADD COLUMN IF NOT EXISTS confidence_score FLOAT
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sdc_verification_status
        ON structured_data_cache(verification_status)
    """)

    # Add initial review columns to structured_data_sources for Phase 5
    op.execute("""
        ALTER TABLE structured_data_sources
        ADD COLUMN IF NOT EXISTS requires_initial_review BOOLEAN DEFAULT true
    """)

    op.execute("""
        ALTER TABLE structured_data_sources
        ADD COLUMN IF NOT EXISTS initial_review_completed_at TIMESTAMPTZ
    """)

    op.execute("""
        ALTER TABLE structured_data_sources
        ADD COLUMN IF NOT EXISTS initial_review_by VARCHAR(100)
    """)

    # Add circuit breaker columns for Phase 4
    op.execute("""
        ALTER TABLE structured_data_sources
        ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER DEFAULT 0
    """)

    op.execute("""
        ALTER TABLE structured_data_sources
        ADD COLUMN IF NOT EXISTS circuit_open_until TIMESTAMPTZ
    """)

    # Mark existing sources as already reviewed (they were manually added)
    op.execute("""
        UPDATE structured_data_sources
        SET requires_initial_review = false,
            initial_review_completed_at = NOW(),
            initial_review_by = 'migration'
        WHERE requires_initial_review IS NULL OR requires_initial_review = true
    """)


def downgrade() -> None:
    # Remove circuit breaker columns
    op.execute("""
        ALTER TABLE structured_data_sources
        DROP COLUMN IF EXISTS circuit_open_until
    """)

    op.execute("""
        ALTER TABLE structured_data_sources
        DROP COLUMN IF EXISTS consecutive_failures
    """)

    # Remove initial review columns
    op.execute("""
        ALTER TABLE structured_data_sources
        DROP COLUMN IF EXISTS initial_review_by
    """)

    op.execute("""
        ALTER TABLE structured_data_sources
        DROP COLUMN IF EXISTS initial_review_completed_at
    """)

    op.execute("""
        ALTER TABLE structured_data_sources
        DROP COLUMN IF EXISTS requires_initial_review
    """)

    # Remove verification columns
    op.execute("""
        ALTER TABLE structured_data_cache
        DROP COLUMN IF EXISTS confidence_score
    """)

    op.execute("""
        ALTER TABLE structured_data_cache
        DROP COLUMN IF EXISTS verification_status
    """)

    op.execute("""
        ALTER TABLE structured_data_cache
        DROP COLUMN IF EXISTS verified_at
    """)

    # Drop audit log table
    op.execute("DROP TABLE IF EXISTS structured_data_audit_log")
