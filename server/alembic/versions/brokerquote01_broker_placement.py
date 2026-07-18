"""Broker-placed carrier quotes — extend insurance_quotes for the broker desk.

Revision ID: brokerquote01
Revises: carrierquote01
Create Date: 2026-07-18

Adds broker placement to the `insurance_quotes` lifecycle table created by
`carrierquote01`, so a broker can quote/present/bind on behalf of a client in
their book — for both on-platform (tenant `companies`) and off-platform
(`broker_external_clients`) clients — and the client can accept a quote the
broker presented (the present->accept path reads the same row).

Changes (all additive / relaxing, no data rewrite):
- `company_id` becomes NULLABLE; a new CHECK requires exactly one of
  `company_id` / `external_client_id` (a quote belongs to a tenant OR an
  off-platform client, never both, never neither). Existing rows all carry
  `company_id`, so they satisfy it.
- `broker_id`, `external_client_id`, `placement`, `presented_at`,
  `commission_bps`, `broker_note` columns.
- The `status` CHECK is widened to add `presented` (broker presented the quote
  to the client for acceptance).

Reversible.
"""

from alembic import op


revision = "brokerquote01"
down_revision = "carrierquote01"
branch_labels = None
depends_on = None


def upgrade():
    # company_id no longer mandatory — off-platform quotes have no companies row.
    op.execute("ALTER TABLE insurance_quotes ALTER COLUMN company_id DROP NOT NULL")

    op.execute(
        "ALTER TABLE insurance_quotes "
        "ADD COLUMN IF NOT EXISTS broker_id UUID REFERENCES brokers(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE insurance_quotes "
        "ADD COLUMN IF NOT EXISTS external_client_id UUID "
        "REFERENCES broker_external_clients(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE insurance_quotes "
        "ADD COLUMN IF NOT EXISTS placement VARCHAR(20) NOT NULL DEFAULT 'client'"
    )
    op.execute("ALTER TABLE insurance_quotes ADD COLUMN IF NOT EXISTS presented_at TIMESTAMPTZ")
    op.execute("ALTER TABLE insurance_quotes ADD COLUMN IF NOT EXISTS commission_bps INTEGER")
    op.execute("ALTER TABLE insurance_quotes ADD COLUMN IF NOT EXISTS broker_note TEXT")

    # placement vocabulary
    op.execute(
        "ALTER TABLE insurance_quotes DROP CONSTRAINT IF EXISTS ck_insurance_quotes_placement"
    )
    op.execute(
        "ALTER TABLE insurance_quotes ADD CONSTRAINT ck_insurance_quotes_placement "
        "CHECK (placement IN ('client', 'broker'))"
    )

    # exactly one subject (tenant company XOR off-platform external client)
    op.execute(
        "ALTER TABLE insurance_quotes DROP CONSTRAINT IF EXISTS ck_insurance_quotes_subject"
    )
    op.execute(
        "ALTER TABLE insurance_quotes ADD CONSTRAINT ck_insurance_quotes_subject "
        "CHECK ((company_id IS NOT NULL) <> (external_client_id IS NOT NULL))"
    )

    # widen the status vocabulary to include 'presented' (broker -> client for accept).
    # The original inline column CHECK is auto-named insurance_quotes_status_check.
    op.execute(
        "ALTER TABLE insurance_quotes DROP CONSTRAINT IF EXISTS insurance_quotes_status_check"
    )
    op.execute(
        "ALTER TABLE insurance_quotes ADD CONSTRAINT insurance_quotes_status_check "
        "CHECK (status IN ('draft','quoted','presented','bound','expired','error'))"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_insurance_quotes_broker "
        "ON insurance_quotes(broker_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_insurance_quotes_external "
        "ON insurance_quotes(external_client_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_insurance_quotes_external")
    op.execute("DROP INDEX IF EXISTS idx_insurance_quotes_broker")

    # restore the original (pre-'presented') status vocabulary
    op.execute(
        "ALTER TABLE insurance_quotes DROP CONSTRAINT IF EXISTS insurance_quotes_status_check"
    )
    op.execute(
        "ALTER TABLE insurance_quotes ADD CONSTRAINT insurance_quotes_status_check "
        "CHECK (status IN ('draft','quoted','bound','expired','error'))"
    )

    op.execute("ALTER TABLE insurance_quotes DROP CONSTRAINT IF EXISTS ck_insurance_quotes_subject")
    op.execute("ALTER TABLE insurance_quotes DROP CONSTRAINT IF EXISTS ck_insurance_quotes_placement")

    op.execute("ALTER TABLE insurance_quotes DROP COLUMN IF EXISTS broker_note")
    op.execute("ALTER TABLE insurance_quotes DROP COLUMN IF EXISTS commission_bps")
    op.execute("ALTER TABLE insurance_quotes DROP COLUMN IF EXISTS presented_at")
    op.execute("ALTER TABLE insurance_quotes DROP COLUMN IF EXISTS placement")
    op.execute("ALTER TABLE insurance_quotes DROP COLUMN IF EXISTS external_client_id")
    op.execute("ALTER TABLE insurance_quotes DROP COLUMN IF EXISTS broker_id")

    # Re-assert NOT NULL on company_id. Any off-platform rows written since the
    # upgrade would block this; delete them first (they cannot exist pre-upgrade).
    op.execute("DELETE FROM insurance_quotes WHERE company_id IS NULL")
    op.execute("ALTER TABLE insurance_quotes ALTER COLUMN company_id SET NOT NULL")
