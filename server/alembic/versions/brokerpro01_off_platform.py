"""Broker Pro: entitlement flag + off-platform (non-tenant) external clients

Revision ID: brokerpro01
Revises: epldeep01
Create Date: 2026-06-20

Adds the **Broker Pro** entitlement (`brokers.plan`) and the **off-platform**
broker layer — clients a broker manages who are NOT Matcha tenants. The broker
keys in their loss-run summary + an EPL questionnaire; the same WC + EPL scoring
engine runs on it. Three tables, parallel to the tenant ones (tenant features
untouched):

- broker_external_clients          — identity + exposure basis (no companies row)
- broker_external_wc               — broker-entered WC loss snapshot + experience mod
- broker_external_epl_attestations — broker's read on all 10 EPL factors

Gated by `brokers.plan = 'pro'` (admin-toggleable).
"""

from alembic import op


revision = "brokerpro01"
down_revision = "epldeep01"
branch_labels = None
depends_on = None


def upgrade():
    # Broker Pro entitlement -----------------------------------------------------
    op.execute(
        """
        ALTER TABLE brokers ADD COLUMN IF NOT EXISTS plan VARCHAR(20) NOT NULL DEFAULT 'standard'
            CHECK (plan IN ('standard', 'pro'))
        """
    )

    # Off-platform external clients ---------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_external_clients (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id     UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            name          VARCHAR(255) NOT NULL,
            industry      VARCHAR(100),
            headcount     INTEGER,
            primary_state VARCHAR(2),
            note          TEXT,
            status        VARCHAR(16) NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'archived')),
            created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_external_clients_broker ON broker_external_clients(broker_id)"
    )

    # WC loss snapshot (broker-keyed off a carrier loss run) ---------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_external_wc (
            external_client_id    UUID PRIMARY KEY REFERENCES broker_external_clients(id) ON DELETE CASCADE,
            period_label          VARCHAR(60),
            recordable_cases      INTEGER NOT NULL DEFAULT 0,
            dart_cases            INTEGER NOT NULL DEFAULT 0,
            lost_days             INTEGER NOT NULL DEFAULT 0,
            restricted_days       INTEGER NOT NULL DEFAULT 0,
            ct_cases              INTEGER NOT NULL DEFAULT 0,
            acute_cases           INTEGER NOT NULL DEFAULT 0,
            post_termination_cases INTEGER NOT NULL DEFAULT 0,
            lost_time_open        INTEGER NOT NULL DEFAULT 0,
            lost_time_resolved    INTEGER NOT NULL DEFAULT 0,
            avg_days_to_rtw       NUMERIC(6, 1),
            current_emr           NUMERIC(5, 3),
            carrier               VARCHAR(255),
            annual_premium        NUMERIC(12, 2),
            updated_by            UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at            TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    # EPL attestations — all 10 factors are broker-attested for off-platform -----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_external_epl_attestations (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            external_client_id UUID NOT NULL REFERENCES broker_external_clients(id) ON DELETE CASCADE,
            item_key           VARCHAR(40) NOT NULL,
            status             VARCHAR(16) NOT NULL DEFAULT 'unknown'
                                 CHECK (status IN ('in_place', 'partial', 'gap', 'unknown')),
            note               TEXT,
            updated_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at         TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_broker_external_epl UNIQUE (external_client_id, item_key)
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS broker_external_epl_attestations")
    op.execute("DROP TABLE IF EXISTS broker_external_wc")
    op.execute("DROP TABLE IF EXISTS broker_external_clients")
    op.execute("ALTER TABLE brokers DROP COLUMN IF EXISTS plan")
