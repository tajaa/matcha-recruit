"""Broker↔company chat — conversations, messages, read receipts.

Revision ID: brokerchat01
Revises: brokerquote03
Create Date: 2026-07-20

A private messaging surface between an HR broker and one of its linked client
companies. The relationship spine already exists (``broker_company_links``);
this adds the conversation store on top of it:

- ``broker_company_conversations`` — one thread between a (broker, company)
  pair. A pair can hold several threads (e.g. one per claim / flagged item),
  each with an optional topic anchor (``reference_*``) pointing at the record
  under discussion (a claim, loss run, document, incident, …).
- ``broker_company_messages`` — the messages. ``sender_side`` records whether
  the author sat on the broker or company side; ``client_message_id`` gives the
  same idempotent-insert story the werk channels use. Each message may also
  carry its own inline reference to a specific shared record.
- ``broker_company_conversation_reads`` — per-user read watermark, so unread
  counts work for both broker members and company users reading the same thread.

Fully reversible.
"""

from alembic import op


revision = "brokerchat01"
down_revision = "brokerquote03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_company_conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            subject TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'archived')),
            reference_type VARCHAR(40),
            reference_id UUID,
            reference_label TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_by_side VARCHAR(10) NOT NULL
                CHECK (created_by_side IN ('broker', 'company')),
            last_message_at TIMESTAMPTZ,
            last_message_preview TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bc_conversations_broker "
        "ON broker_company_conversations(broker_id, last_message_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bc_conversations_company "
        "ON broker_company_conversations(company_id, last_message_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_company_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL
                REFERENCES broker_company_conversations(id) ON DELETE CASCADE,
            sender_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sender_side VARCHAR(10) NOT NULL
                CHECK (sender_side IN ('broker', 'company')),
            body TEXT NOT NULL,
            reference_type VARCHAR(40),
            reference_id UUID,
            reference_label TEXT,
            client_message_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            edited_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bc_messages_conversation "
        "ON broker_company_messages(conversation_id, created_at)"
    )
    # Idempotent send: a retried POST with the same client_message_id from the
    # same sender collapses to the original row (matches channel_messages).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bc_messages_sender_cmid "
        "ON broker_company_messages(sender_user_id, client_message_id) "
        "WHERE client_message_id IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_company_conversation_reads (
            conversation_id UUID NOT NULL
                REFERENCES broker_company_conversations(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            last_read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_read_message_id UUID,
            PRIMARY KEY (conversation_id, user_id)
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS broker_company_conversation_reads")
    op.execute("DROP TABLE IF EXISTS broker_company_messages")
    op.execute("DROP TABLE IF EXISTS broker_company_conversations")
