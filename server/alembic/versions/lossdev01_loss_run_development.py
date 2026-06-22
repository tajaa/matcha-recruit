"""Loss-run triangulation — multi-period loss-run snapshots for development

Revision ID: lossdev01
Revises: limadq01
Create Date: 2026-06-22

Loss-run triangulation (gap-analysis #5/#23). A single loss run is one snapshot;
claims develop (grow) after they're reported. Triangulation lines up the SAME
policy years valued at MULTIPLE dates to measure that development and project
ultimate losses — the reserve-adequacy signal underwriters trust.

``wc_loss_runs`` stores one row per (subject, line, policy period, valuation
date). A broker uploads several historical loss runs (each a valuation date) for
a client — on-platform (``subject_kind='company'``) or off-platform Broker Pro
(``subject_kind='external'``). The chain-ladder engine builds the triangle from
these rows. ``line`` carries WC / GL / auto so the same schema serves all three.
"""

from alembic import op


revision = "lossdev01"
down_revision = "limadq01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wc_loss_runs (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id            UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            subject_kind         VARCHAR(10) NOT NULL
                                   CHECK (subject_kind IN ('company','external')),
            subject_id           UUID NOT NULL,
            line                 VARCHAR(8) NOT NULL DEFAULT 'wc',
            policy_period_label  VARCHAR(40) NOT NULL,
            policy_period_start  DATE,
            valuation_date       DATE NOT NULL,
            claim_count          INTEGER NOT NULL DEFAULT 0,
            open_count           INTEGER NOT NULL DEFAULT 0,
            paid                 NUMERIC(14,2) NOT NULL DEFAULT 0,
            reserved             NUMERIC(14,2) NOT NULL DEFAULT 0,
            source               VARCHAR(60),
            note                 TEXT,
            created_by           UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_wc_loss_runs UNIQUE
                (broker_id, subject_kind, subject_id, line, policy_period_label, valuation_date)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_wc_loss_runs_subject "
        "ON wc_loss_runs(broker_id, subject_kind, subject_id, line)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS wc_loss_runs")
