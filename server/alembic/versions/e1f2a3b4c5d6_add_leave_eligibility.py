"""add_leave_eligibility

Revision ID: e1f2a3b4c5d6
Revises: d0a8f93f3fd0
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str]] = 'd0a8f93f3fd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create leave_jurisdiction_rules table and add eligibility_data to leave_requests."""

    # Add eligibility_data column to leave_requests
    op.execute("""
        ALTER TABLE leave_requests
        ADD COLUMN IF NOT EXISTS eligibility_data JSONB DEFAULT '{}'
    """)

    # Create leave jurisdiction rules table
    op.execute("""
        CREATE TABLE IF NOT EXISTS leave_jurisdiction_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state VARCHAR(2) NOT NULL,
            leave_program VARCHAR(50) NOT NULL,
            program_label VARCHAR(100) NOT NULL,
            paid BOOLEAN DEFAULT false,
            max_weeks INTEGER,
            wage_replacement_pct DECIMAL(5,2),
            employer_size_threshold INTEGER,
            employee_tenure_months INTEGER,
            employee_hours_threshold INTEGER,
            job_protection BOOLEAN DEFAULT true,
            notes TEXT,
            source_url TEXT,
            last_verified_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(state, leave_program)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_jurisdiction_rules_state
            ON leave_jurisdiction_rules(state)
    """)

    # Seed federal + state leave programs
    op.execute("""
        INSERT INTO leave_jurisdiction_rules
            (state, leave_program, program_label, paid, max_weeks,
             wage_replacement_pct, employer_size_threshold,
             employee_tenure_months, employee_hours_threshold,
             job_protection, notes, source_url)
        VALUES
            -- Federal FMLA (applies in all states)
            ('US', 'fmla', 'Family and Medical Leave Act (FMLA)', false, 12,
             NULL, 50, 12, 1250, true,
             'Federal unpaid leave for serious health conditions, new child, or military family needs.',
             'https://www.dol.gov/agencies/whd/fmla'),

            -- California
            ('CA', 'ca_cfra', 'CA Family Rights Act (CFRA)', false, 12,
             NULL, 5, 12, 1250, true,
             'Mirrors FMLA but applies to employers with 5+ employees.',
             'https://www.dfeh.ca.gov/family-medical-pregnancy-leave/'),
            ('CA', 'ca_pdl', 'CA Pregnancy Disability Leave (PDL)', false, 17,
             NULL, 5, NULL, NULL, true,
             'Up to 4 months for pregnancy-related disability. No tenure requirement.',
             'https://www.dfeh.ca.gov/family-medical-pregnancy-leave/'),
            ('CA', 'ca_pfl', 'CA Paid Family Leave (PFL)', true, 8,
             60.00, NULL, NULL, NULL, false,
             'State-funded wage replacement through SDI. No job protection on its own.',
             'https://edd.ca.gov/en/disability/paid-family-leave/'),
            ('CA', 'ca_sdi', 'CA State Disability Insurance (SDI)', true, 52,
             60.00, NULL, NULL, NULL, false,
             'Wage replacement for own medical disability. Funded by payroll deductions.',
             'https://edd.ca.gov/en/disability/'),

            -- New York
            ('NY', 'ny_pfl', 'NY Paid Family Leave (PFL)', true, 12,
             67.00, NULL, NULL, NULL, true,
             'Job-protected paid leave for bonding, family care, or military assistance.',
             'https://paidfamilyleave.ny.gov/'),
            ('NY', 'ny_dbl', 'NY Disability Benefits Law (DBL)', true, 26,
             50.00, NULL, NULL, NULL, false,
             'Short-term disability for off-the-job injuries/illness.',
             'https://www.ny.gov/services/disability-benefits'),

            -- Washington
            ('WA', 'wa_pfml', 'WA Paid Family & Medical Leave (PFML)', true, 12,
             90.00, NULL, NULL, 820, true,
             'Combined family and medical leave. 820 hours in qualifying period.',
             'https://paidleave.wa.gov/'),

            -- New Jersey
            ('NJ', 'nj_fli', 'NJ Family Leave Insurance (FLI)', true, 12,
             85.00, NULL, NULL, NULL, false,
             'Wage replacement for bonding or family care.',
             'https://www.nj.gov/labor/worker-protections/earnedsick/covid.shtml'),
            ('NJ', 'nj_tdi', 'NJ Temporary Disability Insurance (TDI)', true, 26,
             85.00, NULL, NULL, NULL, false,
             'Short-term disability wage replacement.',
             'https://www.nj.gov/labor/worker-protections/earnedsick/covid.shtml'),
            ('NJ', 'nj_fla', 'NJ Family Leave Act (NJFLA)', false, 12,
             NULL, 30, 12, 1000, true,
             'Job-protected unpaid leave for family care. Employers with 30+.',
             'https://www.nj.gov/oag/dcr/law.html'),

            -- Colorado
            ('CO', 'co_famli', 'CO Family and Medical Leave Insurance (FAMLI)', true, 12,
             90.00, NULL, NULL, NULL, true,
             'Paid family and medical leave for all CO workers.',
             'https://famli.colorado.gov/'),

            -- Connecticut
            ('CT', 'ct_pfmla', 'CT Paid Family & Medical Leave (PFMLA)', true, 12,
             95.00, NULL, NULL, NULL, true,
             'Paid family and medical leave. All private employers.',
             'https://ctpaidleave.org/'),

            -- Massachusetts
            ('MA', 'ma_pfml', 'MA Paid Family & Medical Leave (PFML)', true, 12,
             80.00, NULL, NULL, NULL, true,
             'Up to 12 weeks family, 20 weeks medical, 26 weeks combined.',
             'https://www.mass.gov/orgs/department-of-family-and-medical-leave'),

            -- Oregon
            ('OR', 'or_pfml', 'OR Paid Leave Oregon', true, 12,
             100.00, NULL, NULL, NULL, true,
             'Up to 12 weeks (14 for pregnancy). All employers contribute.',
             'https://paidleave.oregon.gov/'),

            -- Rhode Island
            ('RI', 'ri_tci', 'RI Temporary Caregiver Insurance (TCI)', true, 6,
             60.00, NULL, NULL, NULL, false,
             'Wage replacement for bonding or family caregiving.',
             'https://dlt.ri.gov/individuals/temporary-disability-insurance'),
            ('RI', 'ri_tdi', 'RI Temporary Disability Insurance (TDI)', true, 30,
             60.00, NULL, NULL, NULL, false,
             'Short-term disability wage replacement.',
             'https://dlt.ri.gov/individuals/temporary-disability-insurance'),

            -- Washington DC
            ('DC', 'dc_upfl', 'DC Universal Paid Family Leave', true, 12,
             90.00, NULL, NULL, NULL, false,
             'Up to 12 weeks parental, 12 medical, 12 family. Employer-funded.',
             'https://does.dc.gov/page/dc-paid-family-leave'),

            -- Hawaii
            ('HI', 'hi_tdi', 'HI Temporary Disability Insurance (TDI)', true, 26,
             58.00, NULL, NULL, NULL, false,
             'Short-term disability wage replacement.',
             'https://labor.hawaii.gov/dcd/'),
            ('HI', 'hi_hfll', 'HI Family Leave Law (HFLL)', false, 4,
             NULL, 100, 6, NULL, true,
             'Job-protected unpaid leave. Employers with 100+ employees.',
             'https://labor.hawaii.gov/dcd/'),

            -- Minnesota
            ('MN', 'mn_pfml', 'MN Paid Family & Medical Leave', true, 12,
             90.00, NULL, NULL, NULL, true,
             'Effective 2026. Up to 12 weeks family, 12 medical, 20 combined.',
             'https://mn.gov/deed/paidleave/'),

            -- Delaware
            ('DE', 'de_pfml', 'DE Paid Family & Medical Leave', true, 12,
             80.00, 10, NULL, NULL, true,
             'Effective 2026. Employers with 10+ for parental, 25+ for other.',
             'https://dol.delaware.gov/pfml/'),

            -- Maryland
            ('MD', 'md_famli', 'MD Family and Medical Leave Insurance (FAMLI)', true, 12,
             90.00, NULL, NULL, 680, true,
             'Effective 2026. 680 hours in qualifying period.',
             'https://www.labor.maryland.gov/'),

            -- Maine
            ('ME', 'me_pfml', 'ME Paid Family & Medical Leave', true, 12,
             90.00, NULL, NULL, NULL, true,
             'Effective 2026. All employers with 15+ employees.',
             'https://www.maine.gov/labor/')
        ON CONFLICT (state, leave_program) DO NOTHING
    """)


def downgrade() -> None:
    """Drop leave_jurisdiction_rules and remove eligibility_data column."""
    op.execute("DROP TABLE IF EXISTS leave_jurisdiction_rules")
    op.execute("ALTER TABLE leave_requests DROP COLUMN IF EXISTS eligibility_data")
