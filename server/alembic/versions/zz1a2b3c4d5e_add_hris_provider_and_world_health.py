"""Add HRIS provider to provisioning tables and configure World Health as behavioral medicine.

Revision ID: zz1a2b3c4d5e
Revises: zy3z4a5b6c7d
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "zz1a2b3c4d5e"
down_revision = "zy3z4a5b6c7d"
branch_labels = None
depends_on = None

WORLD_HEALTH_ID = "1a1123e5-4c24-4735-8501-9a64a1dd7691"


def upgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Widen provider CHECK constraints to include 'hris'
    # ---------------------------------------------------------------
    for table in (
        "integration_connections",
        "onboarding_runs",
        "external_identities",
        "provisioning_audit_logs",
    ):
        constraint = f"{table}_provider_check"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            f"CHECK (provider IN ('google_workspace', 'slack', 'hris'))"
        )

    # ---------------------------------------------------------------
    # 2. Create hris_sync_runs table
    # ---------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS hris_sync_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            connection_id UUID NOT NULL REFERENCES integration_connections(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed', 'partial')),
            trigger_source VARCHAR(30) NOT NULL DEFAULT 'manual'
                CHECK (trigger_source IN ('manual', 'scheduled', 'api')),
            triggered_by UUID REFERENCES users(id),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            total_records INTEGER DEFAULT 0,
            created_count INTEGER DEFAULT 0,
            updated_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            errors JSONB DEFAULT '[]'::jsonb,
            last_error TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_hris_sync_runs_company
        ON hris_sync_runs(company_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_hris_sync_runs_status
        ON hris_sync_runs(status)
    """)

    # ---------------------------------------------------------------
    # 3. Configure World Health as behavioral medicine institute
    # ---------------------------------------------------------------
    op.execute(f"""
        UPDATE companies
        SET industry = 'Healthcare',
            healthcare_specialties = ARRAY[
                'behavioral_health', 'substance_use_disorder', 'psychiatry',
                'psychology', 'mental_health_counseling', 'applied_behavior_analysis'
            ],
            enabled_features = COALESCE(enabled_features, '{{}}'::jsonb) || '{{"hris_import": true}}'::jsonb
        WHERE id = '{WORLD_HEALTH_ID}'
    """)

    # Add Los Angeles location with behavioral health facility attributes
    op.execute(f"""
        INSERT INTO business_locations (company_id, name, city, state, zipcode, facility_attributes)
        VALUES (
            '{WORLD_HEALTH_ID}',
            'Los Angeles, CA (HQ)',
            'Los Angeles',
            'CA',
            '90012',
            '{{"entity_type": "behavioral_health", "payer_contracts": ["medicare", "medi_cal", "commercial"], "inferred_specialties": ["behavioral_health", "substance_use_disorder", "psychiatry"], "confidence": 1.0}}'::jsonb
        )
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Remove the LA location
    op.execute(f"""
        DELETE FROM business_locations
        WHERE company_id = '{WORLD_HEALTH_ID}'
          AND city = 'Los Angeles' AND name = 'Los Angeles, CA (HQ)'
    """)

    # Revert World Health company fields
    op.execute(f"""
        UPDATE companies
        SET healthcare_specialties = NULL,
            enabled_features = enabled_features - 'hris_import'
        WHERE id = '{WORLD_HEALTH_ID}'
    """)

    # Drop hris_sync_runs table
    op.execute("DROP TABLE IF EXISTS hris_sync_runs")

    # Revert provider CHECK constraints
    for table in (
        "integration_connections",
        "onboarding_runs",
        "external_identities",
        "provisioning_audit_logs",
    ):
        constraint = f"{table}_provider_check"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            f"CHECK (provider IN ('google_workspace', 'slack'))"
        )
