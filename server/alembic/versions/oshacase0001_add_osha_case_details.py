"""add ir_osha_case_details — per-injured-employee OSHA case record

One row per injured employee on a recordable incident: each person's own OSHA
case (classification, days away/restricted, M-column injury type) plus the
Privacy Case answer (privacy_case_reason). Replaces the incident-level single
values for multi-injured incidents and consolidates the privacy answer that
previously lived in category_data.privacy_cases.

case_key = str(employee_id) for a roster employee, or 'reporter' for the
no-roster fallback case — mirrors the per-employee key used by the masking code.
privacy_case_reason is tri-state: NULL = not yet asked, 'none' = asked and
cleared (not a privacy case), else the OSHA reason.

Backfills every existing recordable incident so the 300/301/300A reads have a
case row to render (one per involved employee, or a single 'reporter' row),
copying the current incident-level values + any prior privacy_cases answer.

Revision ID: oshacase0001
Revises: v4w5x6y7z8a9
Create Date: 2026-06-03
"""

from alembic import op


revision = "oshacase0001"
down_revision = "v4w5x6y7z8a9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ir_osha_case_details (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            case_key VARCHAR(64) NOT NULL,
            employee_id UUID,
            case_seq INTEGER NOT NULL DEFAULT 1,
            classification VARCHAR(30),
            days_away INTEGER DEFAULT 0,
            days_restricted INTEGER DEFAULT 0,
            injury_type VARCHAR(30),
            privacy_case_reason VARCHAR(40),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (incident_id, case_key)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_osha_case_details_incident "
        "ON ir_osha_case_details(incident_id);"
    )

    # ── Backfill: one case row per injured employee on each recordable incident ──
    # Roster employees: unnest involved_employee_ids (WITH ORDINALITY → case_seq),
    # copying incident-level classification/days/injury + any prior privacy answer
    # keyed by the employee id in category_data.privacy_cases.
    op.execute(
        """
        INSERT INTO ir_osha_case_details
            (incident_id, case_key, employee_id, case_seq,
             classification, days_away, days_restricted, injury_type, privacy_case_reason)
        SELECT
            i.id,
            emp.eid::text,
            emp.eid,
            emp.ord::int,
            i.osha_classification,
            COALESCE(i.days_away_from_work, 0),
            COALESCE(i.days_restricted_duty, 0),
            i.osha_form_301_data->>'injury_type',
            NULLIF(i.category_data->'privacy_cases'->>(emp.eid::text), '')
        FROM ir_incidents i
        CROSS JOIN LATERAL unnest(i.involved_employee_ids) WITH ORDINALITY AS emp(eid, ord)
        WHERE i.osha_recordable = true
          AND i.involved_employee_ids IS NOT NULL
          AND array_length(i.involved_employee_ids, 1) > 0
        ON CONFLICT (incident_id, case_key) DO NOTHING;
        """
    )
    # Reporter-fallback: recordable incidents with no roster employees get one
    # 'reporter' case row.
    op.execute(
        """
        INSERT INTO ir_osha_case_details
            (incident_id, case_key, employee_id, case_seq,
             classification, days_away, days_restricted, injury_type, privacy_case_reason)
        SELECT
            i.id, 'reporter', NULL, 1,
            i.osha_classification,
            COALESCE(i.days_away_from_work, 0),
            COALESCE(i.days_restricted_duty, 0),
            i.osha_form_301_data->>'injury_type',
            NULLIF(i.category_data->'privacy_cases'->>'reporter', '')
        FROM ir_incidents i
        WHERE i.osha_recordable = true
          AND array_length(i.involved_employee_ids, 1) IS NULL
        ON CONFLICT (incident_id, case_key) DO NOTHING;
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ir_osha_case_details")
