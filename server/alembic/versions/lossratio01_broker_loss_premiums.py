"""Broker-entered paid premium for loss-ratio computation

Revision ID: lossratio01
Revises: legaldef01
Create Date: 2026-06-23

Backs the broker "Loss Ratio" tab (loss ratio = projected ultimate ÷ paid
premium, per policy year). Projected ultimate already comes from the loss-run
triangulation (`wc_loss_runs` → loss_development); this table holds the only
missing input — the premium the client paid the carrier, entered by the broker
per (line, policy period), keyed to line up 1:1 with each loss-run period.

NOTE: branchy alembic history — `down_revision` set to the current tip
(`legaldef01`). Confirm the head for your environment before `alembic upgrade`.
"""

from alembic import op


revision = "lossratio01"
down_revision = "legaldef01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_loss_premiums (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id            UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            subject_kind         VARCHAR(10) NOT NULL CHECK (subject_kind IN ('company','external')),
            subject_id           UUID NOT NULL,
            line                 VARCHAR(8) NOT NULL,
            policy_period_label  VARCHAR(40) NOT NULL,
            paid_premium         NUMERIC(14,2),
            created_by           UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_broker_loss_premiums
                UNIQUE (broker_id, subject_kind, subject_id, line, policy_period_label)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_loss_premiums_subject "
        "ON broker_loss_premiums(broker_id, subject_kind, subject_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS broker_loss_premiums")
