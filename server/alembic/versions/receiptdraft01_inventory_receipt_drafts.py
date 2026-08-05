"""inventory: channel receipt drafts (staged @huume attachment ingest)

A channel admin drags an invoice/packing-slip attachment into a werk
channel and @huume's it — `services/inventory/receipts.py:parse_receipt`
reads the file (CSV deterministic, PDF/image via Gemini), resolves lines
against the roster + open orders, and posts a review pill. This table is
the parsed draft's persisted state between that pill and the admin's
confirm reply — same shape and same reasoning as `schedule_chat_proposals`
(`schedchat01`): a multi-line receipt has nowhere else to live between the
two turns, since (unlike a single order) it isn't one row `inventory_orders`
can carry a JSONB-lines column onto.

`confirm_message_id` is the SAME atomic-claim idiom as
`schedule_chat_proposals.confirm_message_id` / `inventory_orders.
confirm_message_id` / `ems_events.clarify_message_id` — the partial unique
index below is what makes the claim a single indexed probe and guarantees
at most one draft is ever waiting on a given pill. `channels_ws.py`'s
receipt-reply claim slots into the same chain as `_bg_schedule_reply` /
`_bg_inventory_reply`: `UPDATE ... SET confirm_message_id = NULL WHERE
confirm_message_id = $reply_uuid AND status = 'staged' AND created_at >
NOW() - INTERVAL '7 days' RETURNING ...`; a miss falls through to the
normal @huume mention fork, same as every other stale pill in this family.

Committing writes `kind='in'` movements via `receipts.commit_receipt_lines`
with `force=True` — the admin's confirm reply on this draft's review pill
IS the human-review step the provenance invariant (see
services/inventory/CLAUDE.md) requires before a receive can be written.

Revision ID: receiptdraft01
Revises: riskrec01
Create Date: 2026-08-05
"""

from alembic import op


revision = "receiptdraft01"
down_revision = "riskrec01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_receipt_drafts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'staged'
                CHECK (status IN ('staged', 'committed', 'cancelled', 'expired')),
            vendor VARCHAR(200),
            invoice_number VARCHAR(80),
            lines JSONB NOT NULL DEFAULT '[]'::jsonb,
            confirm_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            committed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            committed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_inventory_receipt_drafts_confirm "
        "ON inventory_receipt_drafts(confirm_message_id) WHERE confirm_message_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_receipt_drafts_company "
        "ON inventory_receipt_drafts(company_id, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS inventory_receipt_drafts")
