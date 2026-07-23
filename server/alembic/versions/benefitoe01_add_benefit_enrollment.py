"""benefit enrollment: plan catalog, open enrollment, elections, life events

Revision ID: benefitoe01
Revises: zzzzcappe23
Create Date: 2026-07-23

Extends the existing benefits_admin feature (benefitelig01) with a real
open-enrollment workflow, all FK'd to employees.id (canonical identity) —
NOT benefit_roster_entries, which is a mutable ingest snapshot overwritten
on every CSV/Finch sync.

- benefit_plans / benefit_plan_tiers   — company plan catalog + coverage tiers.
- open_enrollment_periods              — one OPEN period per company at a time
                                          (partial unique index).
- life_event_changes                   — qualifying events opening an
                                          off-cycle election window.
- benefit_elections                    — one election per (employee, plan_type,
                                          window), window = OE period XOR
                                          approved life event. Waive is a
                                          first-class row (plan/tier NULL).
- benefit_enrollment_notices           — claim-before-send dedupe ledger for
                                          the reminder worker.
- benefit_enrollment_audit             — per-domain audit trail, mirrors
                                          ir_audit_log / er_audit_log.

Also seeds the (DISABLED) scheduler_settings row gating the reminder worker.
Enable explicitly post-deploy after dev verification:
    UPDATE scheduler_settings SET enabled = true WHERE task_key = 'benefit_enrollment_notifications';
"""

from alembic import op


revision = "benefitoe01"
down_revision = "zzzzcappe23"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_plans (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            plan_type     VARCHAR(30) NOT NULL,
            name          VARCHAR(200) NOT NULL,
            carrier_name  VARCHAR(160),
            description   TEXT,
            status        VARCHAR(16) NOT NULL DEFAULT 'active',
            waivable      BOOLEAN NOT NULL DEFAULT true,
            metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_benefit_plan UNIQUE (company_id, plan_type, name),
            CONSTRAINT ck_benefit_plan_status CHECK (status IN ('draft', 'active', 'archived'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_benefit_plans_company ON benefit_plans(company_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_plan_tiers (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id        UUID NOT NULL REFERENCES benefit_plans(id) ON DELETE CASCADE,
            coverage_tier  VARCHAR(30) NOT NULL,
            employee_cost  NUMERIC(12,2) NOT NULL DEFAULT 0,
            employer_cost  NUMERIC(12,2) NOT NULL DEFAULT 0,
            cost_period    VARCHAR(16) NOT NULL DEFAULT 'monthly',
            created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_plan_tier UNIQUE (plan_id, coverage_tier),
            CONSTRAINT ck_coverage_tier CHECK (coverage_tier IN
                ('employee_only', 'employee_spouse', 'employee_children', 'family')),
            CONSTRAINT ck_tier_cost_period CHECK (cost_period IN ('monthly', 'per_pay_period'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_benefit_plan_tiers_plan ON benefit_plan_tiers(plan_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS open_enrollment_periods (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name             VARCHAR(200) NOT NULL,
            starts_on        DATE NOT NULL,
            ends_on          DATE NOT NULL,
            plan_year_start  DATE,
            status           VARCHAR(16) NOT NULL DEFAULT 'draft',
            opened_at        TIMESTAMP,
            closed_at        TIMESTAMP,
            created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_oe_dates CHECK (ends_on >= starts_on),
            CONSTRAINT ck_oe_status CHECK (status IN ('draft', 'open', 'closed'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_oe_open_per_company "
        "ON open_enrollment_periods(company_id) WHERE status = 'open'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_oe_company_status ON open_enrollment_periods(company_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS life_event_changes (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id     UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            event_type      VARCHAR(40) NOT NULL,
            event_date      DATE NOT NULL,
            description     TEXT,
            status          VARCHAR(16) NOT NULL DEFAULT 'pending',
            window_days     INTEGER NOT NULL DEFAULT 30,
            window_ends_on  DATE,
            reviewed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at     TIMESTAMP,
            review_note     TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_life_event_status CHECK (status IN ('pending', 'approved', 'denied', 'expired'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_life_event_company_status ON life_event_changes(company_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_life_event_employee ON life_event_changes(employee_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_elections (
            id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id                UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id               UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            open_enrollment_period_id UUID REFERENCES open_enrollment_periods(id) ON DELETE CASCADE,
            life_event_id             UUID REFERENCES life_event_changes(id) ON DELETE CASCADE,
            plan_type                 VARCHAR(30) NOT NULL,
            plan_id                   UUID REFERENCES benefit_plans(id) ON DELETE RESTRICT,
            tier_id                   UUID REFERENCES benefit_plan_tiers(id) ON DELETE RESTRICT,
            waived                    BOOLEAN NOT NULL DEFAULT false,
            dependents                JSONB NOT NULL DEFAULT '[]'::jsonb,
            status                    VARCHAR(16) NOT NULL DEFAULT 'draft',
            submitted_at              TIMESTAMP,
            decided_at                TIMESTAMP,
            decided_by                UUID REFERENCES users(id) ON DELETE SET NULL,
            decision_note             TEXT,
            effective_date            DATE,
            created_at                TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at                TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_election_status CHECK (status IN ('draft', 'submitted', 'approved', 'rejected')),
            CONSTRAINT ck_election_window CHECK (
                num_nonnulls(open_enrollment_period_id, life_event_id) = 1
            ),
            CONSTRAINT ck_election_waive CHECK (
                (waived AND plan_id IS NULL AND tier_id IS NULL)
                OR (NOT waived AND plan_id IS NOT NULL AND tier_id IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_election_oe "
        "ON benefit_elections(employee_id, plan_type, open_enrollment_period_id) "
        "WHERE open_enrollment_period_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_election_le "
        "ON benefit_elections(employee_id, plan_type, life_event_id) "
        "WHERE life_event_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_election_company_status ON benefit_elections(company_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_election_period ON benefit_elections(open_enrollment_period_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_election_employee ON benefit_elections(employee_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_enrollment_notices (
            id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id                UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            open_enrollment_period_id UUID NOT NULL REFERENCES open_enrollment_periods(id) ON DELETE CASCADE,
            employee_id               UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            notice_type               VARCHAR(30) NOT NULL,
            sent_at                   TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_enrollment_notice UNIQUE (open_enrollment_period_id, employee_id, notice_type)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benefit_enrollment_audit (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            actor_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            actor_role     VARCHAR(20),
            entity_type    VARCHAR(30) NOT NULL,
            entity_id      UUID,
            action         VARCHAR(40) NOT NULL,
            detail         JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_benefit_audit_company ON benefit_enrollment_audit(company_id, created_at DESC)"
    )

    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'benefit_enrollment_notifications',
            'Benefit Enrollment Notifications',
            'Auto-opens/closes OE windows; sends window-opened, unsubmitted-nudge, and closing-soon emails.',
            false,
            500
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'benefit_enrollment_notifications'")
    op.execute("DROP TABLE IF EXISTS benefit_enrollment_audit")
    op.execute("DROP TABLE IF EXISTS benefit_enrollment_notices")
    op.execute("DROP INDEX IF EXISTS idx_election_employee")
    op.execute("DROP INDEX IF EXISTS idx_election_period")
    op.execute("DROP INDEX IF EXISTS idx_election_company_status")
    op.execute("DROP INDEX IF EXISTS uq_election_le")
    op.execute("DROP INDEX IF EXISTS uq_election_oe")
    op.execute("DROP TABLE IF EXISTS benefit_elections")
    op.execute("DROP INDEX IF EXISTS idx_life_event_employee")
    op.execute("DROP INDEX IF EXISTS idx_life_event_company_status")
    op.execute("DROP TABLE IF EXISTS life_event_changes")
    op.execute("DROP INDEX IF EXISTS idx_oe_company_status")
    op.execute("DROP INDEX IF EXISTS uq_oe_open_per_company")
    op.execute("DROP TABLE IF EXISTS open_enrollment_periods")
    op.execute("DROP INDEX IF EXISTS idx_benefit_plan_tiers_plan")
    op.execute("DROP TABLE IF EXISTS benefit_plan_tiers")
    op.execute("DROP INDEX IF EXISTS idx_benefit_plans_company")
    op.execute("DROP TABLE IF EXISTS benefit_plans")
