"""Cappe — reviews about a product, from people who bought it.

Reviews were site-wide and anonymous: anyone could post one, about nothing in
particular, and turning submissions off only hid the form.

`cappe_reviews`
  * `product_id` — what the review is about (NULL = the store in general).
  * `order_id` + `verified` — written from a paid order's page, so it comes
    from a buyer. One per product per order.
  * `owner_reply` / `owner_replied_at` — the store's public answer.

`cappe_sites.review_submissions` — who may post: `anyone` (as before),
`buyers` (only from an order page), or `off`. Enforced by the server.

Additive + idempotent.

Revision ID: zzzzcappe47
Revises: zzzzcappe46
"""
from alembic import op

revision = "zzzzcappe47"
down_revision = "zzzzcappe46"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    ALTER TABLE cappe_reviews
        ADD COLUMN IF NOT EXISTS product_id       UUID REFERENCES cappe_products(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS order_id         UUID REFERENCES cappe_orders(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS verified         BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS owner_reply      TEXT,
        ADD COLUMN IF NOT EXISTS owner_replied_at TIMESTAMPTZ
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_reviews_product ON cappe_reviews (product_id, status) "
    "WHERE product_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_reviews_order_product ON cappe_reviews (order_id, product_id) "
    "WHERE order_id IS NOT NULL",
    """
    ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS review_submissions VARCHAR(10) NOT NULL DEFAULT 'anyone'
        CHECK (review_submissions IN ('anyone', 'buyers', 'off'))
    """,
]

_DOWNGRADE = [
    "ALTER TABLE cappe_sites DROP COLUMN IF EXISTS review_submissions",
    "DROP INDEX IF EXISTS uq_cappe_reviews_order_product",
    "DROP INDEX IF EXISTS idx_cappe_reviews_product",
    """
    ALTER TABLE cappe_reviews
        DROP COLUMN IF EXISTS owner_replied_at, DROP COLUMN IF EXISTS owner_reply,
        DROP COLUMN IF EXISTS verified, DROP COLUMN IF EXISTS order_id, DROP COLUMN IF EXISTS product_id
    """,
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
