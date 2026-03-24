"""Add payer_policy_change_log table and staleness columns.

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-03-23
"""

from alembic import op

revision = "r3s4t5u6v7w8"
down_revision = "q2r3s4t5u6v7"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. payer_policy_change_log table ─────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS payer_policy_change_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            policy_id UUID NOT NULL REFERENCES payer_medical_policies(id) ON DELETE CASCADE,
            field_changed VARCHAR(100) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_at TIMESTAMP DEFAULT NOW(),
            change_source VARCHAR(50),
            change_reason TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ppcl_policy
        ON payer_policy_change_log(policy_id, changed_at)
    """)

    # ── 2. Staleness columns on payer_medical_policies ───────────────────
    op.execute("""
        ALTER TABLE payer_medical_policies
        ADD COLUMN IF NOT EXISTS staleness_warning_days INTEGER DEFAULT 90
    """)
    op.execute("""
        ALTER TABLE payer_medical_policies
        ADD COLUMN IF NOT EXISTS staleness_critical_days INTEGER DEFAULT 180
    """)
    op.execute("""
        ALTER TABLE payer_medical_policies
        ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP
    """)

    # Backfill last_verified_at
    op.execute("""
        UPDATE payer_medical_policies
        SET last_verified_at = COALESCE(last_reviewed::timestamp, updated_at, created_at)
        WHERE last_verified_at IS NULL
    """)


def downgrade():
    op.execute("ALTER TABLE payer_medical_policies DROP COLUMN IF EXISTS last_verified_at")
    op.execute("ALTER TABLE payer_medical_policies DROP COLUMN IF EXISTS staleness_critical_days")
    op.execute("ALTER TABLE payer_medical_policies DROP COLUMN IF EXISTS staleness_warning_days")
    op.execute("DROP TABLE IF EXISTS payer_policy_change_log")
