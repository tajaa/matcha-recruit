"""Structured schedule guidance, location timezone, and waiver attestations.

The scheduling branch currently ends at ``empsched05``.  This migration is
additive and keeps all new legal content reviewable before it can be used by a
write-path gate.
"""

from alembic import op


revision = "empsched06"
down_revision = "empsched05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE business_locations "
        "ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_break_rule_sets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE RESTRICT,
            industry_code VARCHAR(80),
            effective_from DATE NOT NULL,
            effective_to DATE,
            rules JSONB NOT NULL,
            citation TEXT NOT NULL,
            authority_url TEXT,
            source_type VARCHAR(20) NOT NULL
                CHECK (source_type IN ('csv', 'api', 'manual', 'legacy_curated')),
            source_external_id VARCHAR(255),
            source_version VARCHAR(100),
            review_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (review_status IN ('pending', 'approved', 'rejected')),
            reviewed_by UUID REFERENCES users(id),
            reviewed_at TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT schedule_break_rule_sets_effective_dates_check
                CHECK (effective_to IS NULL OR effective_to >= effective_from),
            CONSTRAINT schedule_break_rule_sets_rules_object_check
                CHECK (jsonb_typeof(rules) = 'object'),
            CONSTRAINT schedule_break_rule_sets_approval_fields_check
                CHECK (
                    review_status <> 'approved'
                    OR (jurisdiction_id IS NOT NULL AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
                )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_break_rule_sets_lookup
        ON schedule_break_rule_sets(jurisdiction_id, industry_code, effective_from DESC)
        WHERE review_status = 'approved' AND is_active = true
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_break_rule_sets_source
        ON schedule_break_rule_sets(source_type, source_external_id, source_version)
        WHERE source_external_id IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_compliance_attestations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            attestation_type VARCHAR(60) NOT NULL
                CHECK (attestation_type IN ('meal_break_waiver_on_file')),
            value BOOLEAN NOT NULL,
            effective_from DATE NOT NULL,
            confirmed_by UUID NOT NULL REFERENCES users(id),
            confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            note TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_compliance_attestations_current
        ON employee_compliance_attestations(
            company_id, employee_id, attestation_type, effective_from DESC, confirmed_at DESC
        )
        """
    )

    op.execute(
        """
        ALTER TABLE schedule_shift_assignments
            ADD COLUMN IF NOT EXISTS manager_note TEXT,
            ADD COLUMN IF NOT EXISTS manager_note_visible_to_employee BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN IF NOT EXISTS manager_note_include_in_location_digest BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN IF NOT EXISTS manager_note_send_employee_notice BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN IF NOT EXISTS manager_note_updated_by UUID REFERENCES users(id),
            ADD COLUMN IF NOT EXISTS manager_note_updated_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS compliance_guidance JSONB,
            ADD COLUMN IF NOT EXISTS guidance_evaluated_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS guidance_ruleset_hash VARCHAR(64)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE schedule_shift_assignments
            DROP COLUMN IF EXISTS guidance_ruleset_hash,
            DROP COLUMN IF EXISTS guidance_evaluated_at,
            DROP COLUMN IF EXISTS compliance_guidance,
            DROP COLUMN IF EXISTS manager_note_updated_at,
            DROP COLUMN IF EXISTS manager_note_updated_by,
            DROP COLUMN IF EXISTS manager_note_send_employee_notice,
            DROP COLUMN IF EXISTS manager_note_include_in_location_digest,
            DROP COLUMN IF EXISTS manager_note_visible_to_employee,
            DROP COLUMN IF EXISTS manager_note
        """
    )
    op.execute("DROP TABLE IF EXISTS employee_compliance_attestations")
    op.execute("DROP INDEX IF EXISTS idx_schedule_break_rule_sets_source")
    op.execute("DROP INDEX IF EXISTS idx_schedule_break_rule_sets_lookup")
    op.execute("DROP TABLE IF EXISTS schedule_break_rule_sets")
    op.execute("ALTER TABLE business_locations DROP COLUMN IF EXISTS timezone")
