"""Incident-triggered discipline: approval state, templates, sweep ledger.

Adds the sixth Huume skill's schema: incident -> handbook policy check ->
drafted disciplinary action -> HR approval or documented denial -> manager
delivery -> signed letter filed on both the incident and the employee file.

  - company_discipline_templates: per-company letter templates. Created
    BEFORE the progressive_discipline ALTER that FKs it.
  - progressive_discipline gains approval state (approval_status default
    'not_required' — every existing/direct-issue record is unaffected),
    provenance (source_incident_id, template_id), and a STAGED remedial
    training column (pending_remedial_requirement_id) so an
    approval-pending draft never assigns real training before HR decides
    (a denied record must leave nothing behind).
  - status CHECK gains 'denied' (terminal — no un-deny path). Verified none
    of the 6 transition_status callsites in
    routes/employee_lifecycle/discipline.py carries 'denied' in its
    expected_from list, so the new value is inert to every existing
    transition.
  - clients.is_hr_approver: HR-approval-request audience. Shapes
    notification targeting only — approve/deny routes stay
    require_admin_or_client for every business admin, designation is not
    authorization.
  - ir_incident_documents.document_type CHECK gains 'disciplinary' so a
    signed letter can be filed against the incident with a real label
    (route allowlist + client DOC_TYPE_OPTIONS are widened in the same PR,
    not by this migration).
  - discipline_policy_sweep_log: one-shot-ever-per-incident dedupe ledger
    for the Celery sweep (modeled on hr_proactive_push_log, but UNIQUE on
    incident_id alone since there is exactly one subject dimension here).
    A row with thread_id NULL means "checked, nothing found" — that state
    must be stamped too, or a clean incident gets re-Gemini'd every cycle.
  - scheduler_settings row 'discipline_policy_sweep', seeded DISABLED
    (repo convention, see hrpush01).

NOTE: asyncpg's prepared-statement protocol rejects multi-statement SQL in a
single execute() — every DROP CONSTRAINT + ADD CONSTRAINT pair below is two
op.execute() calls, not one string with two statements.

Revision ID: discipapp01
Revises: hrpush01
Create Date: 2026-07-28
"""

from alembic import op


revision = "discipapp01"
down_revision = "hrpush01"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Letter templates — created first, progressive_discipline.template_id FKs it.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_discipline_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            infraction_type VARCHAR(64),
            discipline_type VARCHAR(30),
            body TEXT NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_company_discipline_templates_default "
        "ON company_discipline_templates(company_id) WHERE is_default AND is_active"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_discipline_templates_company "
        "ON company_discipline_templates(company_id) WHERE is_active"
    )

    # 2. Approval state + provenance on the record itself. One decision by one
    #    actor on one row — not a workflow table.
    op.execute(
        """
        ALTER TABLE progressive_discipline
          ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) NOT NULL DEFAULT 'not_required',
          ADD COLUMN IF NOT EXISTS approval_requested_at TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS approved_by UUID REFERENCES users(id),
          ADD COLUMN IF NOT EXISTS approval_decided_at TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS denial_reason TEXT,
          ADD COLUMN IF NOT EXISTS source_incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL,
          ADD COLUMN IF NOT EXISTS template_id UUID REFERENCES company_discipline_templates(id) ON DELETE SET NULL,
          ADD COLUMN IF NOT EXISTS pending_remedial_requirement_id UUID REFERENCES training_requirements(id) ON DELETE SET NULL
        """
    )
    op.execute(
        "ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_approval_status_check"
    )
    op.execute(
        """
        ALTER TABLE progressive_discipline ADD CONSTRAINT progressive_discipline_approval_status_check
          CHECK (approval_status IN ('not_required','pending','approved','denied'))
        """
    )

    # 3. New terminal status value.
    op.execute(
        "ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_status_check"
    )
    op.execute(
        """
        ALTER TABLE progressive_discipline ADD CONSTRAINT progressive_discipline_status_check
          CHECK (status IN ('draft','pending_meeting','pending_signature','active','completed','expired','escalated','denied'))
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_progressive_discipline_approval "
        "ON progressive_discipline(company_id, approval_status) WHERE approval_status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_progressive_discipline_source_incident "
        "ON progressive_discipline(source_incident_id) WHERE source_incident_id IS NOT NULL"
    )

    # 4. HR-approver designation. Notification targeting only.
    op.execute(
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_hr_approver BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # 5. Widen the incident-document type vocabulary for filed signed letters.
    op.execute(
        "ALTER TABLE ir_incident_documents DROP CONSTRAINT IF EXISTS ir_incident_documents_document_type_check"
    )
    op.execute(
        """
        ALTER TABLE ir_incident_documents ADD CONSTRAINT ir_incident_documents_document_type_check
          CHECK (document_type IN ('photo','form','statement','other','disciplinary'))
        """
    )

    # 6. Sweep dedupe ledger.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS discipline_policy_sweep_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            incident_id UUID NOT NULL UNIQUE REFERENCES ir_incidents(id) ON DELETE CASCADE,
            thread_id UUID,
            finding_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # 7. Scheduler row, seeded disabled.
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'discipline_policy_sweep',
            'Incident Policy-Check Sweep',
            'Checks closed incidents against the company handbook and opens a '
            'pre-briefed Huume thread on a finding. One Gemini call per incident; '
            'default off.',
            false,
            25
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'discipline_policy_sweep'")
    op.execute("DROP TABLE IF EXISTS discipline_policy_sweep_log")

    op.execute(
        "ALTER TABLE ir_incident_documents DROP CONSTRAINT IF EXISTS ir_incident_documents_document_type_check"
    )
    op.execute(
        """
        ALTER TABLE ir_incident_documents ADD CONSTRAINT ir_incident_documents_document_type_check
          CHECK (document_type IN ('photo','form','statement','other'))
        """
    )

    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS is_hr_approver")
    op.execute("DROP INDEX IF EXISTS idx_progressive_discipline_source_incident")
    op.execute("DROP INDEX IF EXISTS idx_progressive_discipline_approval")

    op.execute(
        "ALTER TABLE progressive_discipline DROP CONSTRAINT IF EXISTS progressive_discipline_status_check"
    )
    op.execute(
        """
        ALTER TABLE progressive_discipline ADD CONSTRAINT progressive_discipline_status_check
          CHECK (status IN ('draft','pending_meeting','pending_signature','active','completed','expired','escalated'))
        """
    )

    op.execute(
        """
        ALTER TABLE progressive_discipline
          DROP CONSTRAINT IF EXISTS progressive_discipline_approval_status_check,
          DROP COLUMN IF EXISTS pending_remedial_requirement_id,
          DROP COLUMN IF EXISTS template_id,
          DROP COLUMN IF EXISTS source_incident_id,
          DROP COLUMN IF EXISTS denial_reason,
          DROP COLUMN IF EXISTS approval_decided_at,
          DROP COLUMN IF EXISTS approved_by,
          DROP COLUMN IF EXISTS approval_requested_at,
          DROP COLUMN IF EXISTS approval_status
        """
    )

    op.execute("DROP TABLE IF EXISTS company_discipline_templates")
