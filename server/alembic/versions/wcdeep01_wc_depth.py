"""workers-comp depth: claim taxonomy + RTW + NCCI state rates + experience-mod trajectory

Revision ID: wcdeep01
Revises: labor01
Create Date: 2026-06-20

Deepens the broker Workers' Comp surface so Matcha's incident data lines up with
how carriers actually underwrite WC (per WTW *Insurance Marketplace Realities
2026*). Three additions:

1. ir_incidents claim depth — three nullable columns so a recordable can be typed
   the way an underwriter reads it:
     - wc_claim_type        acute vs cumulative_trauma (CT). The report flags CT
                            as the rising medical-severity driver.
     - post_termination     CT/claims filed after the worker left (40% of CT per
                            WCIRB; more litigious). Drives loss-development risk.
     - return_to_work_date  closes a lost-time claim → powers RTW metrics, the
                            carrier "medical management" differentiator.
   All nullable / default-safe so existing recordables read as untyped, not-post-
   term, RTW-open. No backfill required.

2. wc_state_rates — per-state NCCI loss-cost rate trend overlay (the "WC Risk
   Index" jurisdiction lens). Seeded from the report's 2026 filing table + the
   emerging-increase states + the national average. Editable later.

3. company_wc_mods — experience-modification-rate (EMR / "mod") trajectory per
   client. The mod is THE number carriers price WC on; the report stresses mods
   can RISE even where rates fall (ELRs drop). Broker-recorded per policy period.
"""

from alembic import op


revision = "wcdeep01"
down_revision = "labor01"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. ir_incidents claim-depth columns ──────────────────────────────────
    op.execute(
        """
        ALTER TABLE ir_incidents
            ADD COLUMN IF NOT EXISTS wc_claim_type VARCHAR(20)
                CHECK (wc_claim_type IN ('acute', 'cumulative_trauma', 'unknown'))
        """
    )
    op.execute(
        """
        ALTER TABLE ir_incidents
            ADD COLUMN IF NOT EXISTS post_termination BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        ALTER TABLE ir_incidents
            ADD COLUMN IF NOT EXISTS return_to_work_date DATE
        """
    )

    # ── 2. wc_state_rates: NCCI loss-cost rate trend per state ────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wc_state_rates (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state                 VARCHAR(2) NOT NULL,
            loss_cost_change_pct  NUMERIC(6, 2) NOT NULL,
            effective_date        DATE NOT NULL,
            trend                 VARCHAR(10) NOT NULL DEFAULT 'flat'
                                    CHECK (trend IN ('increase', 'decrease', 'flat')),
            source                TEXT,
            note                  TEXT,
            updated_at            TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_wc_state_rate UNIQUE (state, effective_date)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_wc_state_rates_state ON wc_state_rates(state)"
    )

    # Seed: 2026 NCCI filings (report p.32) + emerging-increase states + national
    # average. ON CONFLICT keeps this idempotent and non-destructive of edits.
    op.execute(
        """
        INSERT INTO wc_state_rates (state, loss_cost_change_pct, effective_date, trend, source, note)
        VALUES
            ('MD', -12.3, DATE '2026-01-01', 'decrease', 'NCCI 2026 filing', NULL),
            ('CO',  -6.9, DATE '2026-01-01', 'decrease', 'NCCI 2026 filing', NULL),
            ('FL',  -6.9, DATE '2026-01-01', 'decrease', 'NCCI 2026 filing', NULL),
            ('ME',  -4.8, DATE '2026-04-01', 'decrease', 'NCCI 2026 filing', NULL),
            ('NJ',  -4.3, DATE '2026-01-01', 'decrease', 'NCCI 2026 filing', NULL),
            ('CT',  -3.8, DATE '2026-01-01', 'decrease', 'NCCI 2026 filing', 'exec-officer payroll caps up for 2026'),
            ('TN',  -2.0, DATE '2026-03-01', 'decrease', 'NCCI 2026 filing', NULL),
            ('MO',   1.3, DATE '2026-01-01', 'increase', 'NCCI 2026 filing', 'emerging increase'),
            ('NV',  21.9, DATE '2026-01-01', 'increase', 'NCCI 2026 filing', 'emerging increase'),
            ('DC',   1.7, DATE '2026-01-01', 'increase', 'NCCI 2026 filing', 'emerging increase'),
            ('MT',   0.5, DATE '2026-01-01', 'increase', 'NCCI 2026 filing', 'emerging increase'),
            ('US',  -4.2, DATE '2026-01-01', 'decrease', 'NCCI 2026 filing', 'national average (narrowed from -6.0% in 2024)')
        ON CONFLICT ON CONSTRAINT uq_wc_state_rate DO NOTHING
        """
    )

    # ── 3. company_wc_mods: experience-mod (EMR) trajectory per client ─────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_wc_mods (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id           UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            broker_id            UUID REFERENCES brokers(id) ON DELETE SET NULL,
            policy_period_start  DATE NOT NULL,
            policy_period_end    DATE,
            experience_mod       NUMERIC(5, 3) NOT NULL,
            carrier              VARCHAR(255),
            annual_premium       NUMERIC(12, 2),
            note                 TEXT,
            recorded_by          UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_company_wc_mod UNIQUE (company_id, policy_period_start)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_wc_mods_company ON company_wc_mods(company_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_wc_mods")
    op.execute("DROP TABLE IF EXISTS wc_state_rates")
    op.execute("ALTER TABLE ir_incidents DROP COLUMN IF EXISTS return_to_work_date")
    op.execute("ALTER TABLE ir_incidents DROP COLUMN IF EXISTS post_termination")
    op.execute("ALTER TABLE ir_incidents DROP COLUMN IF EXISTS wc_claim_type")
