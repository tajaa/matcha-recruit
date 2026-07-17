"""Bind a requirement's PENALTY to the authority section that states it

Revision ID: penaltyauth01
Revises: reqstatus01
Create Date: 2026-07-17

`metadata->'penalties'` holds figures nobody sourced: 1,023 of 1,818 catalog rows
carry a penalty block, ZERO carry `grounding`, and 593 have no `source_url` at
all. They are model recall captured at different moments, and it shows — the OSHA
serious-violation maximum exists in the catalog in four vintages simultaneously
(16,131 / 15,873 / 161,323 / 165,514), one of them filed under the agency
"CMS / State Licensing Boards / OSHA". A live tenant is shown $16,131 for an OSHA
violation; 29 CFR 1903.15(d)(3) says $16,550.

The fix is the same one the citation trio already applies to obligations: bind the
number to the text that states it. Two columns and a timestamp, mirroring
`citation_item_id` / `citation_verified_at`.

**Why this is its own binding and not a reuse of citation_item_id:** a penalty is
stated in a DIFFERENT section from the obligation. 29 CFR 1910.147 says lock out
the machine; 29 CFR 1903.15(d) says what it costs. One requirement therefore has
two authorities — what it must do, and what breaking it costs — and they live in
different parts of the CFR.

`penalty_effective_date` is parsed from the schedule's own text ("penalties
proposed after January 15, 2025"), NOT from the item's `amendment_date`: eCFR
reports amendment_date 2017-01-01 for 1903.15 while its body states the 2025
adjustment, so the metadata date is eight years stale and cannot be the freshness
signal. `body_hash` (already maintained by body_fetch) is what actually moves when
the January adjustment lands.
"""

from alembic import op


revision = "penaltyauth01"
down_revision = "reqstatus01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS penalty_item_id UUID
                REFERENCES authority_index_items(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS penalty_verified_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS penalty_effective_date DATE
        """
    )
    # The bind pass and the staleness check both scan "rows bound to this item".
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_jurisdiction_requirements_penalty_item "
        "ON jurisdiction_requirements (penalty_item_id) "
        "WHERE penalty_item_id IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_jurisdiction_requirements_penalty_item")
    op.execute(
        """
        ALTER TABLE jurisdiction_requirements
            DROP COLUMN IF EXISTS penalty_effective_date,
            DROP COLUMN IF EXISTS penalty_verified_at,
            DROP COLUMN IF EXISTS penalty_item_id
        """
    )
