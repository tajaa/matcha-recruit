"""Extend training_* schema for SB 1343 lessons + certs.

Adds:
- training_lesson_templates: global per-variant lesson + quiz content (CA 1hr / 2hr)
- training_quiz_attempts: every employee attempt, audit trail, retake-friendly
- training_requirements: template_id FK, required_minutes, pass_score_percent, applies_to CHECK
- training_records: started_at, attested_at, attestation_ip, attestation_text,
                    certificate_url, certificate_id, retention_until, assigned_by
- employees.is_supervisor BOOLEAN
- scheduler_settings row for 'training_cadence' (default disabled)

Revision ID: zzzz2a3b4c5d6
Revises: zzzy1z2a3b4c5
Create Date: 2026-05-06
"""
from alembic import op


revision = "zzzz2a3b4c5d6"
down_revision = "zzzy1z2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # training_lesson_templates: global content (one per template_key+version)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS training_lesson_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            template_key VARCHAR(80) NOT NULL,
            variant VARCHAR(40) NOT NULL,
            jurisdiction VARCHAR(8) NOT NULL,
            training_type VARCHAR(50) NOT NULL,
            title VARCHAR(255) NOT NULL,
            required_minutes INTEGER NOT NULL,
            frequency_months INTEGER NOT NULL DEFAULT 24,
            lesson_content JSONB NOT NULL,
            quiz JSONB NOT NULL,
            pass_score_percent INTEGER NOT NULL DEFAULT 80,
            version INTEGER NOT NULL DEFAULT 1,
            model_used VARCHAR(80),
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            UNIQUE (template_key, version)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_training_lesson_templates_key_active "
        "ON training_lesson_templates(template_key, is_active)"
    )

    # training_requirements: template link + minutes + pass score + applies_to constraint
    op.execute(
        """
        ALTER TABLE training_requirements
            ADD COLUMN IF NOT EXISTS template_id UUID,
            ADD COLUMN IF NOT EXISTS required_minutes INTEGER,
            ADD COLUMN IF NOT EXISTS pass_score_percent INTEGER NOT NULL DEFAULT 80
        """
    )
    op.execute(
        """
        UPDATE training_requirements
        SET applies_to = 'all'
        WHERE applies_to NOT IN ('all','supervisor','nonsupervisor')
        """
    )
    # Drop existing constraint if it exists, then re-add
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_training_requirements_applies_to'
            ) THEN
                ALTER TABLE training_requirements
                    ADD CONSTRAINT chk_training_requirements_applies_to
                    CHECK (applies_to IN ('all','supervisor','nonsupervisor'));
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_training_requirements_template'
            ) THEN
                ALTER TABLE training_requirements
                    ADD CONSTRAINT fk_training_requirements_template
                    FOREIGN KEY (template_id)
                    REFERENCES training_lesson_templates(id)
                    ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # training_records: lesson progress, attestation, cert, retention, assigned_by
    op.execute(
        """
        ALTER TABLE training_records
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS attested_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS attestation_ip VARCHAR(45),
            ADD COLUMN IF NOT EXISTS attestation_text TEXT,
            ADD COLUMN IF NOT EXISTS certificate_url TEXT,
            ADD COLUMN IF NOT EXISTS certificate_id UUID,
            ADD COLUMN IF NOT EXISTS retention_until DATE,
            ADD COLUMN IF NOT EXISTS assigned_by UUID REFERENCES users(id) ON DELETE SET NULL
        """
    )

    # training_quiz_attempts: per-attempt audit trail
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS training_quiz_attempts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            record_id UUID NOT NULL REFERENCES training_records(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            attempt_number INTEGER NOT NULL,
            answers JSONB NOT NULL,
            score_percent NUMERIC(5,2) NOT NULL,
            passed BOOLEAN NOT NULL,
            elapsed_seconds INTEGER,
            started_at TIMESTAMPTZ,
            submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_training_quiz_attempts_record "
        "ON training_quiz_attempts(record_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_training_quiz_attempts_record_attempt "
        "ON training_quiz_attempts(record_id, attempt_number)"
    )

    # employees.is_supervisor — explicit flag, default false
    op.execute(
        """
        ALTER TABLE employees
            ADD COLUMN IF NOT EXISTS is_supervisor BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_employees_supervisor "
        "ON employees(org_id) WHERE is_supervisor = TRUE"
    )

    # Scheduler row for cadence task — default disabled
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'training_cadence',
            'Training Cadence',
            'Auto-assign SB 1343 trainings to CA employees and renew expiring records.',
            false,
            200
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'training_cadence'")

    op.execute("DROP INDEX IF EXISTS idx_employees_supervisor")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS is_supervisor")

    op.execute("DROP INDEX IF EXISTS idx_training_quiz_attempts_record_attempt")
    op.execute("DROP INDEX IF EXISTS idx_training_quiz_attempts_record")
    op.execute("DROP TABLE IF EXISTS training_quiz_attempts")

    op.execute(
        """
        ALTER TABLE training_records
            DROP COLUMN IF EXISTS assigned_by,
            DROP COLUMN IF EXISTS retention_until,
            DROP COLUMN IF EXISTS certificate_id,
            DROP COLUMN IF EXISTS certificate_url,
            DROP COLUMN IF EXISTS attestation_text,
            DROP COLUMN IF EXISTS attestation_ip,
            DROP COLUMN IF EXISTS attested_at,
            DROP COLUMN IF EXISTS started_at
        """
    )

    op.execute(
        """
        ALTER TABLE training_requirements
            DROP CONSTRAINT IF EXISTS fk_training_requirements_template,
            DROP CONSTRAINT IF EXISTS chk_training_requirements_applies_to,
            DROP COLUMN IF EXISTS pass_score_percent,
            DROP COLUMN IF EXISTS required_minutes,
            DROP COLUMN IF EXISTS template_id
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_training_lesson_templates_key_active")
    op.execute("DROP TABLE IF EXISTS training_lesson_templates")
