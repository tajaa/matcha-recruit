"""backfill leave_jurisdiction_rules into jurisdiction_requirements

Ports leave program data from the legacy leave_jurisdiction_rules table
into the unified jurisdiction_requirements system (category='leave').
Metadata JSON is stored in `description` (TEXT) to avoid the VARCHAR(100)
limit on current_value.

Revision ID: y7z8a9b0c1d2
Revises: x6y7z8a9b0c1
Create Date: 2026-03-09
"""

from alembic import op
from sqlalchemy import text


revision = "y7z8a9b0c1d2"
down_revision = (
    "x6y7z8a9b0c1",
    "o6p7q8r9s0t1",
    "a1b2c3d4e5f9",
    "s1t2u3v4w5x6",
    "t2u3v4w5x6y7",
    "u3v4w5x6y7z8",
    "v4w5x6y7z8a9",
    "w5x6y7z8a9b0",
)
branch_labels = None
depends_on = None


def upgrade():
    # Guard: skip if leave_jurisdiction_rules doesn't exist yet
    conn = op.get_bind()
    has_table = conn.execute(
        text("SELECT to_regclass('public.leave_jurisdiction_rules') IS NOT NULL")
    ).scalar()
    if not has_table:
        return

    # Ensure state-level jurisdiction rows exist
    op.execute("""
        INSERT INTO jurisdictions (city, state)
        SELECT DISTINCT '', UPPER(ljr.state)
        FROM leave_jurisdiction_rules ljr
        WHERE ljr.state != 'US'
        ON CONFLICT (city, state) DO NOTHING
    """)

    # Backfill leave programs into jurisdiction_requirements.
    # Metadata JSON goes into `description` (TEXT, no length limit).
    # A short human-readable summary goes into `current_value` (VARCHAR 100).
    op.execute("""
        INSERT INTO jurisdiction_requirements
            (jurisdiction_id, requirement_key, category,
             jurisdiction_level, jurisdiction_name,
             title, description, current_value, numeric_value,
             source_url, last_verified_at)
        SELECT
            j.id,
            ljr.leave_program,
            'leave',
            CASE WHEN ljr.state = 'US' THEN 'federal' ELSE 'state' END,
            CASE WHEN ljr.state = 'US' THEN 'Federal' ELSE ljr.state END,
            ljr.program_label,
            json_build_object(
                'paid', ljr.paid,
                'max_weeks', ljr.max_weeks,
                'wage_pct', ljr.wage_replacement_pct,
                'job_prot', ljr.job_protection,
                'emp_min', ljr.employer_size_threshold,
                'tenure_mo', ljr.employee_tenure_months,
                'hrs_min', ljr.employee_hours_threshold
            )::TEXT,
            LEFT(
                CONCAT_WS(', ',
                    CASE WHEN ljr.max_weeks IS NOT NULL
                         THEN ljr.max_weeks || ' weeks' END,
                    CASE WHEN ljr.wage_replacement_pct IS NOT NULL
                         THEN ljr.wage_replacement_pct || '% pay' END,
                    CASE WHEN ljr.job_protection THEN 'job protected' END,
                    CASE WHEN ljr.paid THEN 'paid' END
                ), 100
            ),
            ljr.max_weeks,
            ljr.source_url,
            COALESCE(ljr.last_verified_at, NOW())
        FROM leave_jurisdiction_rules ljr
        JOIN jurisdictions j ON j.state = UPPER(ljr.state) AND j.city = ''
        WHERE ljr.state != 'US'
        ON CONFLICT (jurisdiction_id, requirement_key) DO NOTHING
    """)


def downgrade():
    op.execute("""
        DELETE FROM jurisdiction_requirements WHERE category = 'leave'
    """)
