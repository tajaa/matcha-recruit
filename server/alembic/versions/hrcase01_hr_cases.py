"""HR cases: incident -> write-up -> approval -> delivery -> signed copy.

A standalone record for the whole corrective-action workflow. It does NOT
write progressive_discipline (that module is retired); an HR case carries its
own lifecycle:

  flagged -> drafting -> hr_review -> (changes_requested -> hr_review)*
          -> approved -> delivered -> verifying -> closed
  needs_attention sits between verifying and closed when the signed copy has
  a problem; dismissed ends a case that shouldn't go further.

- hr_case_settings: per-company case numbering, filename template for signed
  copies, and the intake-triage confidence threshold.
- hr_case_events: append-only trail (stage moves, checks, decisions).
- hr_case_triage_log: one row per (incident, phase) ever, claimed BEFORE the
  model call so a retry or a second close never re-checks or re-notifies.
  implicated IS NULL means "the check couldn't run", never "clean".

draft_file_id / signed_file_id point at Matcha Drive (mdrive01).

Revision ID: hrcase01
Revises: mdrive02
Create Date: 2026-09-29
"""

from alembic import op


revision = "hrcase01"
down_revision = "mdrive02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_case_settings (
            company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            next_seq INTEGER NOT NULL DEFAULT 0,
            filename_template TEXT NOT NULL
                DEFAULT '{last_name}_{first_name}_{action_type}_{delivered_date}',
            triage_min_confidence NUMERIC(3, 2) NOT NULL DEFAULT 0.60
                CHECK (triage_min_confidence BETWEEN 0 AND 1),
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            case_number VARCHAR(20) NOT NULL,
            origin VARCHAR(16) NOT NULL
                CHECK (origin IN ('intake_triage', 'close_check', 'gm_draft', 'huume', 'manual')),
            stage VARCHAR(20) NOT NULL DEFAULT 'flagged'
                CHECK (stage IN ('flagged', 'drafting', 'hr_review', 'changes_requested', 'approved',
                                 'delivered', 'verifying', 'needs_attention', 'closed', 'dismissed')),
            source_incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL,
            employee_id UUID REFERENCES employees(id) ON DELETE SET NULL,
            action_type VARCHAR(20)
                CHECK (action_type IN ('verbal_warning', 'written_warning', 'final_warning',
                                       'suspension', 'pip', 'other')),
            occurrence_dates DATE[] NOT NULL DEFAULT '{}',
            gm_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            opened_by UUID REFERENCES users(id) ON DELETE SET NULL,
            thread_id UUID REFERENCES mw_threads(id) ON DELETE SET NULL,
            draft_file_id UUID REFERENCES drive_files(id) ON DELETE SET NULL,
            signed_file_id UUID REFERENCES drive_files(id) ON DELETE SET NULL,
            triage JSONB,
            review JSONB,
            verification JSONB,
            decision VARCHAR(20) CHECK (decision IN ('approved', 'changes_requested')),
            decision_reason TEXT,
            decided_by UUID REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMPTZ,
            delivered_at TIMESTAMPTZ,
            delivered_by UUID REFERENCES users(id) ON DELETE SET NULL,
            attention_reasons TEXT[] NOT NULL DEFAULT '{}',
            attention_acknowledged_by UUID REFERENCES users(id) ON DELETE SET NULL,
            attention_acknowledged_at TIMESTAMPTZ,
            dismissed_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_hr_cases_number ON hr_cases (company_id, case_number)")
    # At most one open case per incident: the intake flag, the close re-check,
    # a GM draft and Huume all converge on it instead of opening duplicates.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_hr_cases_open_incident ON hr_cases (source_incident_id) "
        "WHERE source_incident_id IS NOT NULL AND stage NOT IN ('closed', 'dismissed')"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_hr_cases_company_stage ON hr_cases (company_id, stage, updated_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hr_cases_gm ON hr_cases (gm_user_id) WHERE gm_user_id IS NOT NULL")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_case_events (
            id BIGSERIAL PRIMARY KEY,
            case_id UUID NOT NULL REFERENCES hr_cases(id) ON DELETE CASCADE,
            actor_user_id UUID,
            event VARCHAR(40) NOT NULL,
            from_stage VARCHAR(20),
            to_stage VARCHAR(20),
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_hr_case_events_case ON hr_case_events (case_id, created_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_case_triage_log (
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            phase VARCHAR(8) NOT NULL CHECK (phase IN ('intake', 'close')),
            company_id UUID NOT NULL,
            implicated BOOLEAN,
            result JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (incident_id, phase)
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS hr_case_triage_log")
    op.execute("DROP TABLE IF EXISTS hr_case_events")
    op.execute("DROP TABLE IF EXISTS hr_cases")
    op.execute("DROP TABLE IF EXISTS hr_case_settings")
