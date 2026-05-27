"""broker risk alerts: negative-trend WC/safety alerts for brokers

Revision ID: brokerrisk01
Revises: osha300a01
Create Date: 2026-05-27

Adds the state table backing the automated broker risk-trend alert feature and
seeds the (disabled) scheduler_settings row that gates its periodic Celery task.

Design notes:
- One row per (broker, company, metric_key) via a UNIQUE constraint — this is
  both the de-dup key (so the 15-min worker doesn't re-email the same trend) and
  the read source for the broker-facing alerts panel.
- resolved_at NULL = trend currently firing; set when the rule stops firing, so
  a later re-fire is treated as a fresh alert (re-arm).
- premium_direction is persisted because estimate_premium_impact() is
  benchmark-relative (a snapshot), not a period-over-period delta — the worker
  compares this stored direction against the new one to detect a flip.
- Scheduler row seeded DISABLED. Enable explicitly post-deploy after dev
  verification (UPDATE scheduler_settings SET enabled=true WHERE
  task_key='broker_risk_alerts').
"""

from alembic import op


revision = "brokerrisk01"
down_revision = "osha300a01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_risk_alerts (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id         UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            metric_key        VARCHAR(40) NOT NULL,
            severity          VARCHAR(16) NOT NULL DEFAULT 'warning',
            current_value     NUMERIC,
            prior_value       NUMERIC,
            delta_pct         NUMERIC,
            premium_direction VARCHAR(16),
            message           TEXT,
            metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
            first_alerted_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            last_alerted_at   TIMESTAMP NOT NULL DEFAULT NOW(),
            last_evaluated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            resolved_at       TIMESTAMP,
            is_read           BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT uq_broker_risk_alert UNIQUE (broker_id, company_id, metric_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_risk_alerts_broker
            ON broker_risk_alerts(broker_id, last_alerted_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_risk_alerts_active
            ON broker_risk_alerts(broker_id) WHERE resolved_at IS NULL
        """
    )

    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'broker_risk_alerts',
            'Broker Risk Alerts',
            'Emails brokers when an assigned client''s WC/safety metrics show a negative 12-month trend.',
            false,
            200
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'broker_risk_alerts'")
    op.execute("DROP INDEX IF EXISTS idx_broker_risk_alerts_active")
    op.execute("DROP INDEX IF EXISTS idx_broker_risk_alerts_broker")
    op.execute("DROP TABLE IF EXISTS broker_risk_alerts")
