"""Add discipline engine fields and supporting tables.

Extends progressive_discipline with infraction_type, severity, lookback_months,
expires_at, escalation chain, override metadata, and signature workflow columns.

Adds discipline_policy_mapping (per-company config that drives the escalation
engine) and discipline_audit_log (state-change history).

Backfills existing rows so the engine treats legacy records as fully-resolved.

Revision ID: zzzi5j6k7l8m9
Revises: zzzh4i5j6k7l8
Create Date: 2026-04-29
"""
from alembic import op


revision = "zzzi5j6k7l8m9"
down_revision = "zzzh4i5j6k7l8"
branch_labels = None
depends_on = None


def upgrade():
    # ── progressive_discipline: new columns ──────────────────────────
    op.execute("""
        ALTER TABLE progressive_discipline
            ADD COLUMN IF NOT EXISTS infraction_type VARCHAR(64) NOT NULL DEFAULT 'unspecified',
            ADD COLUMN IF NOT EXISTS severity VARCHAR(20) NOT NULL DEFAULT 'moderate',
            ADD COLUMN IF NOT EXISTS lookback_months INTEGER NOT NULL DEFAULT 6,
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS escalated_from_id UUID REFERENCES progressive_discipline(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS override_level BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS override_reason TEXT,
            ADD COLUMN IF NOT EXISTS signature_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS signature_requested_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS signature_completed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS signature_envelope_id VARCHAR(255),
            ADD COLUMN IF NOT EXISTS signed_pdf_storage_path VARCHAR(500),
            ADD COLUMN IF NOT EXISTS meeting_held_at TIMESTAMPTZ
    """)

    # severity CHECK
    op.execute("""
        ALTER TABLE progressive_discipline
        DROP CONSTRAINT IF EXISTS progressive_discipline_severity_check
    """)
    op.execute("""
        ALTER TABLE progressive_discipline
        ADD CONSTRAINT progressive_discipline_severity_check
        CHECK (severity IN ('minor', 'moderate', 'severe', 'immediate_written'))
    """)

    # signature_status CHECK
    op.execute("""
        ALTER TABLE progressive_discipline
        DROP CONSTRAINT IF EXISTS progressive_discipline_signature_status_check
    """)
    op.execute("""
        ALTER TABLE progressive_discipline
        ADD CONSTRAINT progressive_discipline_signature_status_check
        CHECK (signature_status IN ('pending', 'requested', 'signed', 'refused', 'physical_uploaded'))
    """)

    # status CHECK — extend with pending_meeting / pending_signature
    op.execute("""
        ALTER TABLE progressive_discipline
        DROP CONSTRAINT IF EXISTS progressive_discipline_status_check
    """)
    op.execute("""
        ALTER TABLE progressive_discipline
        ADD CONSTRAINT progressive_discipline_status_check
        CHECK (status IN ('draft', 'pending_meeting', 'pending_signature', 'active', 'completed', 'expired', 'escalated'))
    """)

    # Backfill expires_at + signature_status for legacy rows
    op.execute("""
        UPDATE progressive_discipline
        SET expires_at = (issued_date::timestamptz + INTERVAL '6 months')
        WHERE expires_at IS NULL
    """)
    op.execute("""
        UPDATE progressive_discipline
        SET signature_status = 'signed'
        WHERE signature_status = 'pending' AND status IN ('active', 'completed', 'expired', 'escalated')
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_progressive_discipline_expires_active
        ON progressive_discipline(expires_at) WHERE status = 'active'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_progressive_discipline_signature_envelope
        ON progressive_discipline(signature_envelope_id)
        WHERE signature_envelope_id IS NOT NULL
    """)

    # ── discipline_policy_mapping ────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS discipline_policy_mapping (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            infraction_type VARCHAR(64) NOT NULL,
            label VARCHAR(255) NOT NULL,
            default_severity VARCHAR(20) NOT NULL DEFAULT 'moderate'
                CHECK (default_severity IN ('minor', 'moderate', 'severe', 'immediate_written')),
            lookback_months_minor INTEGER NOT NULL DEFAULT 6,
            lookback_months_moderate INTEGER NOT NULL DEFAULT 9,
            lookback_months_severe INTEGER NOT NULL DEFAULT 12,
            auto_to_written BOOLEAN NOT NULL DEFAULT FALSE,
            notify_grandparent_manager BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, infraction_type)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_discipline_policy_mapping_company
        ON discipline_policy_mapping(company_id)
    """)

    # ── discipline_audit_log ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS discipline_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            discipline_id UUID NOT NULL REFERENCES progressive_discipline(id) ON DELETE CASCADE,
            actor_user_id UUID REFERENCES users(id),
            action VARCHAR(40) NOT NULL,
            details JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_discipline_audit_log_discipline
        ON discipline_audit_log(discipline_id, created_at DESC)
    """)

    # ── scheduler_settings seed ──────────────────────────────────────
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'discipline_expiry',
            'Discipline Expiry Sweep',
            'Flips active discipline records past expires_at to expired and writes audit rows.',
            FALSE,
            10000
        )
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'discipline_expiry'")
    op.execute("DROP TABLE IF EXISTS discipline_audit_log")
    op.execute("DROP TABLE IF EXISTS discipline_policy_mapping")

    op.execute("DROP INDEX IF EXISTS idx_progressive_discipline_signature_envelope")
    op.execute("DROP INDEX IF EXISTS idx_progressive_discipline_expires_active")

    op.execute("ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_status_check")
    op.execute("""
        ALTER TABLE progressive_discipline
        ADD CONSTRAINT progressive_discipline_status_check
        CHECK (status IN ('active', 'completed', 'expired', 'escalated'))
    """)
    op.execute("ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_signature_status_check")
    op.execute("ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_severity_check")

    op.execute("""
        ALTER TABLE progressive_discipline
            DROP COLUMN IF EXISTS meeting_held_at,
            DROP COLUMN IF EXISTS signed_pdf_storage_path,
            DROP COLUMN IF EXISTS signature_envelope_id,
            DROP COLUMN IF EXISTS signature_completed_at,
            DROP COLUMN IF EXISTS signature_requested_at,
            DROP COLUMN IF EXISTS signature_status,
            DROP COLUMN IF EXISTS override_reason,
            DROP COLUMN IF EXISTS override_level,
            DROP COLUMN IF EXISTS escalated_from_id,
            DROP COLUMN IF EXISTS expires_at,
            DROP COLUMN IF EXISTS lookback_months,
            DROP COLUMN IF EXISTS severity,
            DROP COLUMN IF EXISTS infraction_type
    """)
