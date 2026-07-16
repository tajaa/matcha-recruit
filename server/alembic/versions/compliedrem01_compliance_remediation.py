"""Compliance remediation trail — issue lifecycle state + immutable audit log

Revision ID: compliedrem01
Revises: compilot01
Create Date: 2026-07-16

Backs the risk-cockpit remediation feature. Compliance issues (wage / credential
/ incident / alert) are computed live by `services/compliance_risk.py`; nothing
recorded that an issue existed, got fixed, when, how, or by whom. That trail is
the value — it documents remediation for ER cases / legal defense.

`compliance_issue_state` is the lifecycle tracker: one row per (company,
issue_key), upserted every time the risk summary is computed. A key that was
open and is no longer produced by the live check flips to `resolved`
(auto-documented); a manager can `dismiss` a false positive. `basis` holds the
raw observed values (pay_rate/threshold, expiry, status) so a dismissed issue
re-surfaces only when the numbers actually change, and so the trail can render
"pay $17.00 → $18.42".

`compliance_remediation_audit_log` is the append-only, ER-grade record of every
status transition (opened / auto_resolved / dismissed / reopened / reactivated /
noted), mirroring the ir/er audit shape (`entity_type`/`entity_id` polymorphic).
"""

from alembic import op


revision = "compliedrem01"
down_revision = "compilot01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS compliance_issue_state (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            issue_key         TEXT NOT NULL,
            source            VARCHAR(20) NOT NULL
                                CHECK (source IN ('wage','credential','incident','alert')),
            entity_type       VARCHAR(20),
            entity_id         TEXT,
            employee_id       UUID REFERENCES employees(id) ON DELETE SET NULL,
            title             TEXT,
            detail            TEXT,
            severity          VARCHAR(12),
            penalty           JSONB,
            statute_citation  TEXT,
            basis             JSONB,
            status            VARCHAR(12) NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open','resolved','dismissed')),
            first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at       TIMESTAMPTZ,
            resolved_by       UUID REFERENCES users(id) ON DELETE SET NULL,
            resolution_method VARCHAR(30),
            resolution_note   TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, issue_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_issue_state_company_status "
        "ON compliance_issue_state (company_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_issue_state_resolved "
        "ON compliance_issue_state (company_id, resolved_at DESC) "
        "WHERE status IN ('resolved','dismissed')"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS compliance_remediation_audit_log (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            issue_key      TEXT NOT NULL,
            entity_type    VARCHAR(20),
            entity_id      TEXT,
            action         VARCHAR(20) NOT NULL,
            actor_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            details        JSONB,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_remediation_audit_company "
        "ON compliance_remediation_audit_log (company_id, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS compliance_remediation_audit_log")
    op.execute("DROP TABLE IF EXISTS compliance_issue_state")
