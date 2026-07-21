"""Client-controlled sharing of incident defense files with a broker.

Revision ID: irshare01
Revises: brokerchat01
Create Date: 2026-07-21

Brokers could list and download the full claims-readiness packet — narrative,
witnesses, employee names, corrective actions — for EVERY incident of every
linked client. That is the client's record, not the broker's, and nothing about
the broker relationship implies consent to all of it.

This table inverts the default: the broker sees an incident's defense file only
where the client has explicitly shared that incident with that broker. A row IS
the grant; revoking deletes it (no tombstone — a share is a present-tense state,
not an event log, and the audit trail for who-shared-what lives on the row while
it exists).

Keyed on (incident, broker) rather than (incident) so a client with two brokers
can share a sensitive incident with one and not the other. Access still also
requires a live ``broker_company_links`` row, so a terminated broker loses
everything regardless of the shares left behind.

Fully reversible.
"""

from alembic import op


revision = "irshare01"
down_revision = "brokerchat01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_incident_shares (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            shared_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (incident_id, broker_id)
        )
        """
    )
    # The broker read path is "this broker's shares within this company".
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_incident_shares_broker_company
        ON broker_incident_shares(broker_id, company_id)
        """
    )
    # The company read path is "which brokers is this incident shared with".
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_incident_shares_incident
        ON broker_incident_shares(incident_id)
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS broker_incident_shares")
