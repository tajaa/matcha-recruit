"""labor relations phase 1: CBA store + clause library + grievance workflow

Revision ID: labor01
Revises: devicetok01
Create Date: 2026-06-19

Backs the Pro-bundled Labor Relations feature (`labor_relations` flag). Phase 1
adds the CBA document store + AI clause library and the grievance workflow with
contractual step-deadlines:

- lr_cbas                      — one collective-bargaining agreement (metadata;
                                the PDF lives in private S3, path stored here).
                                `grievance_step_config` JSONB is the contractual
                                deadline source of truth (AI-seeded, HR-confirmed).
- lr_cba_clauses              — clause library (manual or AI-extracted) a
                                grievance can cite as violated.
- lr_grievances              — the core grievance record.
- lr_grievance_violated_clauses — M:N grievance ↔ cited clause.
- lr_grievance_steps         — per-step escalation timeline carrying the
                                computed contractual deadlines + alert state.
- lr_audit_log               — one audit table for the whole labor package.

Also:
- Seeds the (DISABLED) scheduler_settings row gating the daily deadline-alert
  Celery sweep. Enable post-deploy after dev verification:
      UPDATE scheduler_settings SET enabled = true WHERE task_key = 'grievance_deadline_alerts';
- Backfills `labor_relations=true` onto existing Pro (bespoke/invite/legacy-NULL,
  non-personal) companies, since the flag is stored-at-signup (NOT a tier
  overlay) so pre-existing rows would otherwise lack it.
"""

from alembic import op


revision = "labor01"
down_revision = "devicetok01"
branch_labels = None
depends_on = None


def upgrade():
    # ── lr_cbas ───────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lr_cbas (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id             UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            union_name             VARCHAR(255) NOT NULL,
            union_local            VARCHAR(100),
            bargaining_unit_desc   TEXT,
            effective_date         DATE,
            expiration_date        DATE,
            status                 VARCHAR(20) NOT NULL DEFAULT 'active'
                                     CHECK (status IN ('draft','active','expired','superseded','in_negotiation')),
            document_storage_path  VARCHAR(500),
            document_filename      VARCHAR(255),
            extracted_text         TEXT,
            extraction_status      VARCHAR(20) NOT NULL DEFAULT 'pending'
                                     CHECK (extraction_status IN ('pending','processing','complete','failed','skipped')),
            renewal_alert_days     INTEGER NOT NULL DEFAULT 90,
            -- Array of step objects, each with fields step (int), name,
            -- file_within_days, respond_within_days, day_basis (calendar|working).
            grievance_step_config  JSONB NOT NULL DEFAULT '[]'::jsonb,
            grievance_steps_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
            metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by             UUID REFERENCES users(id),
            created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_lr_cbas_company ON lr_cbas(company_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lr_cbas_expiration "
        "ON lr_cbas(expiration_date) WHERE status = 'active'"
    )

    # ── lr_cba_clauses ────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lr_cba_clauses (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cba_id          UUID NOT NULL REFERENCES lr_cbas(id) ON DELETE CASCADE,
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            article_number  VARCHAR(50),
            title           VARCHAR(300),
            clause_text     TEXT NOT NULL,
            category        VARCHAR(40)
                              CHECK (category IN ('wages','hours','seniority','grievance_procedure',
                                'discipline','just_cause','overtime','benefits','union_security',
                                'management_rights','health_safety','layoff_recall','holidays_leave','other')),
            source          VARCHAR(20) NOT NULL DEFAULT 'manual'
                              CHECK (source IN ('manual','ai_extracted')),
            ai_confidence   NUMERIC(4,3),
            sort_order      INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_lr_cba_clauses_cba ON lr_cba_clauses(cba_id, sort_order)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_lr_cba_clauses_company ON lr_cba_clauses(company_id)")

    # ── lr_grievances ─────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lr_grievances (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id            UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            grievance_number      VARCHAR(50) NOT NULL,
            cba_id                UUID REFERENCES lr_cbas(id) ON DELETE SET NULL,
            grievant_employee_id  UUID REFERENCES employees(id) ON DELETE SET NULL,
            is_class_grievance    BOOLEAN NOT NULL DEFAULT FALSE,
            steward_employee_id   UUID REFERENCES employees(id) ON DELETE SET NULL,
            steward_name_external VARCHAR(255),
            title                 VARCHAR(255) NOT NULL,
            description           TEXT,
            grievance_type        VARCHAR(40)
                                    CHECK (grievance_type IN ('discipline','discharge','contract_interpretation',
                                      'pay_wages','seniority','overtime','working_conditions','health_safety',
                                      'management_rights','past_practice','other')),
            incident_date         DATE,
            filed_date            DATE,
            current_step          INTEGER NOT NULL DEFAULT 1,
            status                VARCHAR(25) NOT NULL DEFAULT 'draft'
                                    CHECK (status IN ('draft','filed','in_progress','advanced','resolved',
                                      'withdrawn','denied','arbitration','settled')),
            resolution            VARCHAR(25)
                                    CHECK (resolution IN ('granted','denied','partially_granted','withdrawn',
                                      'settled','arbitrated_win','arbitrated_loss')),
            resolution_summary    TEXT,
            resolved_at           TIMESTAMPTZ,
            linked_discipline_id  UUID REFERENCES progressive_discipline(id) ON DELETE SET NULL,
            linked_er_case_id     UUID REFERENCES er_cases(id) ON DELETE SET NULL,
            documents             JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_by            UUID REFERENCES users(id),
            assigned_to           UUID REFERENCES users(id),
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_lr_grievance_number UNIQUE (company_id, grievance_number)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_lr_grievances_company ON lr_grievances(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_lr_grievances_status ON lr_grievances(company_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_lr_grievances_grievant ON lr_grievances(grievant_employee_id)")

    # ── lr_grievance_violated_clauses (M:N) ───────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lr_grievance_violated_clauses (
            grievance_id  UUID NOT NULL REFERENCES lr_grievances(id) ON DELETE CASCADE,
            clause_id     UUID NOT NULL REFERENCES lr_cba_clauses(id) ON DELETE CASCADE,
            PRIMARY KEY (grievance_id, clause_id)
        )
        """
    )

    # ── lr_grievance_steps (per-step timeline + contractual deadlines) ─────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lr_grievance_steps (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            grievance_id         UUID NOT NULL REFERENCES lr_grievances(id) ON DELETE CASCADE,
            company_id           UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            step_number          INTEGER NOT NULL,
            step_name            VARCHAR(100) NOT NULL,
            status               VARCHAR(20) NOT NULL DEFAULT 'pending'
                                   CHECK (status IN ('pending','active','responded','advanced','resolved',
                                     'skipped','missed_deadline')),
            filed_at             TIMESTAMPTZ,
            deadline_to_respond  DATE,
            deadline_to_advance  DATE,
            response_received_at TIMESTAMPTZ,
            heard_by_user_id     UUID REFERENCES users(id),
            management_response  TEXT,
            union_position       TEXT,
            outcome              VARCHAR(20)
                                   CHECK (outcome IN ('granted','denied','partially_granted','advanced')),
            deadline_alert_sent  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_lr_grievance_step UNIQUE (grievance_id, step_number)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lr_grievance_steps_deadline "
        "ON lr_grievance_steps(deadline_to_respond) "
        "WHERE status = 'active' AND deadline_alert_sent = FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lr_grievance_steps_grievance "
        "ON lr_grievance_steps(grievance_id, step_number)"
    )

    # ── lr_audit_log (shared across the labor package) ────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lr_audit_log (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            entity_type   VARCHAR(30) NOT NULL,
            entity_id     UUID NOT NULL,
            actor_user_id UUID REFERENCES users(id),
            action        VARCHAR(40) NOT NULL,
            details       JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lr_audit_entity "
        "ON lr_audit_log(entity_type, entity_id, created_at DESC)"
    )

    # ── scheduler row (DISABLED) for the daily deadline-alert sweep ───────────
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'grievance_deadline_alerts',
            'Grievance Deadline Alerts',
            'Daily: flags grievance steps whose contractual response/advance deadline is near or missed, emails the HR owner + steward, and marks truly-missed steps.',
            false,
            500
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )

    # ── Backfill: grant labor_relations to existing Pro companies ─────────────
    # The flag is stored-at-signup (auth.py + admin 'bespoke' preset), NOT a
    # TIER_REQUIRED overlay, so companies created before this change lack it.
    # Personal Werk (is_personal=true) shares signup_source='bespoke' and MUST
    # stay excluded.
    op.execute(
        """
        UPDATE companies
        SET enabled_features = jsonb_set(
            COALESCE(enabled_features, '{}')::jsonb, '{labor_relations}', 'true'::jsonb
        )
        WHERE (signup_source IN ('bespoke','invite') OR signup_source IS NULL)
          AND is_personal IS NOT TRUE
        """
    )


def downgrade():
    op.execute("UPDATE companies SET enabled_features = enabled_features - 'labor_relations'")
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'grievance_deadline_alerts'")
    op.execute("DROP TABLE IF EXISTS lr_audit_log")
    op.execute("DROP TABLE IF EXISTS lr_grievance_steps")
    op.execute("DROP TABLE IF EXISTS lr_grievance_violated_clauses")
    op.execute("DROP TABLE IF EXISTS lr_grievances")
    op.execute("DROP TABLE IF EXISTS lr_cba_clauses")
    op.execute("DROP TABLE IF EXISTS lr_cbas")
