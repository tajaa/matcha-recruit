"""huume: cross-type asset registry

Every durable artifact a Huume turn creates (offer letter, discipline
record, incident report, schedule change, inventory row, ...) becomes one
row here — a name, a pointer to the real domain row, and which thread/company
it came from. Written from a single choke point,
`actions.execute_huume_action`'s tail, after each staged action's executor
returns `{status: "created", record_id, ...}` — see
`services/huume/assets.py`. `draft_offer_letter` (a WRITE tool, not staged)
gets its own explicit call site since it never reaches that dispatch.

No status column: the underlying row's status drifts independently of this
registry (an offer moves draft->sent->accepted from the public candidate
endpoint, a discipline record moves through the HR approval queue, an
inventory order moves through receive/cancel) — the listing route hydrates
status live per `ref_table` instead of trying to keep a duplicate in sync.

`UNIQUE (company_id, ref_table, ref_id)` makes the write an upsert: a
re-send of an already-drafted offer, or a discipline decision on a record a
prior draft already registered, refreshes the label on the SAME row rather
than duplicating it.

Revision ID: huumeasset01
Revises: receiptdraft01
Create Date: 2026-08-05
"""

from alembic import op


revision = "huumeasset01"
down_revision = "receiptdraft01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS huume_assets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            thread_id UUID REFERENCES mw_threads(id) ON DELETE SET NULL,
            asset_type VARCHAR(50) NOT NULL,
            ref_table VARCHAR(50) NOT NULL,
            ref_id VARCHAR(255) NOT NULL,
            label TEXT NOT NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'huume_action'
                CHECK (source IN ('huume_action', 'draft')),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, ref_table, ref_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_huume_assets_thread "
        "ON huume_assets(thread_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_huume_assets_company_type "
        "ON huume_assets(company_id, asset_type, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS huume_assets")
