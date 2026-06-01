"""benefit eligibility + renewal risk: roster store, exceptions, risk radar

Revision ID: benefitelig01
Revises: irlink0002
Create Date: 2026-06-01

Backs the employee-benefits broker feature (Scopes 1 & 2):

- benefit_roster_entries        — source-agnostic per-employee snapshot fed by
                                  EITHER a Finch sync OR a CSV upload. The
                                  detectors read only from here.
- benefit_eligibility_exceptions — Scope 1 output (new-hire enrollment gaps +
                                  terminated-but-still-deducted premium leaks).
                                  De-duped per (company, dedup_key).
- benefit_renewal_risk          — Scope 2 output: one row per
                                  (company, dimension_type, dimension_value);
                                  the prior row's values are the rolling baseline.

Also seeds the (DISABLED) scheduler_settings row gating the daily Celery sync.
Enable explicitly post-deploy after dev verification:
    UPDATE scheduler_settings SET enabled = true WHERE task_key = 'benefit_eligibility_sync';
"""

from alembic import op


revision = "benefitelig01"
down_revision = "irlink0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_roster_entries (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id                      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            source                          VARCHAR(20) NOT NULL,
            external_id                     VARCHAR(160) NOT NULL,
            employee_id                     UUID REFERENCES employees(id) ON DELETE SET NULL,
            first_name                      VARCHAR(160),
            last_name                       VARCHAR(160),
            email                           VARCHAR(320),
            department                      VARCHAR(160),
            location                        VARCHAR(160),
            start_date                      DATE,
            termination_date                DATE,
            employment_status               VARCHAR(20) NOT NULL DEFAULT 'active',
            has_benefits_enrollment         BOOLEAN,
            employer_health_premium_monthly NUMERIC(12,2),
            gross_pay_period                NUMERIC(14,2),
            benefit_line_items              JSONB NOT NULL DEFAULT '[]'::jsonb,
            snapshot_date                   DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at                      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at                      TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_benefit_roster_entry UNIQUE (company_id, source, external_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_benefit_roster_company ON benefit_roster_entries(company_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_eligibility_exceptions (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id             UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            dedup_key              VARCHAR(220) NOT NULL,
            roster_entry_id        UUID REFERENCES benefit_roster_entries(id) ON DELETE SET NULL,
            employee_id            UUID REFERENCES employees(id) ON DELETE SET NULL,
            employee_name          VARCHAR(320),
            exception_type         VARCHAR(40) NOT NULL,
            reference_date         DATE NOT NULL,
            days_elapsed           INTEGER,
            days_remaining         INTEGER,
            estimated_monthly_leak NUMERIC(12,2),
            status                 VARCHAR(20) NOT NULL DEFAULT 'open',
            source                 VARCHAR(20),
            detected_at            TIMESTAMP NOT NULL DEFAULT NOW(),
            last_seen_at           TIMESTAMP NOT NULL DEFAULT NOW(),
            resolved_at            TIMESTAMP,
            resolution_note        TEXT,
            last_nudge_sent_at     TIMESTAMP,
            metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT uq_benefit_exception UNIQUE (company_id, dedup_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_benefit_exception_company_status "
        "ON benefit_eligibility_exceptions(company_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_renewal_risk (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id               UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            dimension_type           VARCHAR(20) NOT NULL DEFAULT 'company',
            dimension_value          VARCHAR(200) NOT NULL DEFAULT '',
            risk_band                VARCHAR(16) NOT NULL DEFAULT 'stable',
            turnover_pct             NUMERIC,
            turnover_baseline_pct    NUMERIC,
            turnover_delta_pct       NUMERIC,
            lost_workdays            INTEGER NOT NULL DEFAULT 0,
            lost_workdays_baseline   NUMERIC,
            lost_workdays_delta_pct  NUMERIC,
            near_misses              INTEGER NOT NULL DEFAULT 0,
            behavioral_incidents     INTEGER NOT NULL DEFAULT 0,
            headcount                INTEGER NOT NULL DEFAULT 0,
            gross_payroll            NUMERIC(16,2),
            policy_month             INTEGER,
            triggers                 JSONB NOT NULL DEFAULT '[]'::jsonb,
            computed_at              TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at               TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at               TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_benefit_renewal_risk UNIQUE (company_id, dimension_type, dimension_value)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_benefit_renewal_risk_company "
        "ON benefit_renewal_risk(company_id)"
    )

    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'benefit_eligibility_sync',
            'Benefit Eligibility Sync',
            'Daily: ingests benefits rosters (Finch), detects new-hire enrollment gaps + terminated-but-still-deducted premium leaks, and recomputes renewal-risk.',
            false,
            500
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'benefit_eligibility_sync'")
    op.execute("DROP INDEX IF EXISTS idx_benefit_renewal_risk_company")
    op.execute("DROP TABLE IF EXISTS benefit_renewal_risk")
    op.execute("DROP INDEX IF EXISTS idx_benefit_exception_company_status")
    op.execute("DROP TABLE IF EXISTS benefit_eligibility_exceptions")
    op.execute("DROP INDEX IF EXISTS idx_benefit_roster_company")
    op.execute("DROP TABLE IF EXISTS benefit_roster_entries")
