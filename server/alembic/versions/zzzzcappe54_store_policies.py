"""Cappe — store policies and the seller's identity on receipts.

A store had no refund, shipping, terms or privacy page, nothing in its footer
or at checkout pointing to one, and receipts named the business and nothing
else — an EU/UK seller can't issue a VAT invoice without its address and VAT
number, and buyers had no billing address on theirs.

`cappe_site_policies(site_id, kind, body)` — one text per kind (refund,
shipping, terms, privacy), served at `/policies/<kind>` on the store and
linked from its footer, its sitemap, the bag and Stripe's payment page.
Plain text; no row = no page.

`cappe_sites.legal_name`, `business_address`, `tax_id` — who is selling, on
every receipt. `collect_phone` — Stripe's page asks the buyer for a phone
number (couriers want one).

`cappe_orders.billing_address` — the buyer's name, phone and billing address
as Stripe collected them (Stripe's `customer_details`), for the receipt.

Additive; the downgrade drops the table and the columns.

Revision ID: zzzzcappe54
Revises: zzzzcappe53
Create Date: 2026-10-20
"""
from alembic import op

revision = "zzzzcappe54"
down_revision = "zzzzcappe53"
branch_labels = None
depends_on = None


_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_site_policies (
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        kind VARCHAR(16) NOT NULL CHECK (kind IN ('refund', 'shipping', 'terms', 'privacy')),
        body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 20000),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (site_id, kind)
    )
    """,
    "ALTER TABLE cappe_sites "
    "ADD COLUMN IF NOT EXISTS legal_name VARCHAR(200), "
    "ADD COLUMN IF NOT EXISTS business_address VARCHAR(500), "
    "ADD COLUMN IF NOT EXISTS tax_id VARCHAR(64), "
    "ADD COLUMN IF NOT EXISTS collect_phone BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS billing_address JSONB",
]

_DOWNGRADE = [
    "ALTER TABLE cappe_orders DROP COLUMN IF EXISTS billing_address",
    "ALTER TABLE cappe_sites DROP COLUMN IF EXISTS collect_phone, DROP COLUMN IF EXISTS tax_id, "
    "DROP COLUMN IF EXISTS business_address, DROP COLUMN IF EXISTS legal_name",
    "DROP TABLE IF EXISTS cappe_site_policies",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
