"""Cappe — taking a deposit (or the full price) when someone books.

`cappe_booking_types.payment_mode` — `none` (as before: book now, pay at the
appointment), `deposit` (`deposit_cents` now, the rest at the appointment) or
`full`. A paid booking is made as an order with one booking line, so it uses
everything orders already have: the Stripe payment page, its expiry, the
abandoned-order sweep, pay-after-approval, refunds. The booking is held
(`pending`) until the payment lands; a hold nobody pays for is released.

`cappe_order_items.balance_due_cents` — what is still owed at the appointment
after a deposit.

Additive + idempotent.

Revision ID: zzzzcappe49
Revises: zzzzcappe48
"""
from alembic import op

revision = "zzzzcappe49"
down_revision = "zzzzcappe48"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    ALTER TABLE cappe_booking_types
        ADD COLUMN IF NOT EXISTS payment_mode  VARCHAR(10) NOT NULL DEFAULT 'none'
            CHECK (payment_mode IN ('none', 'deposit', 'full')),
        ADD COLUMN IF NOT EXISTS deposit_cents INTEGER CHECK (deposit_cents > 0)
    """,
    "ALTER TABLE cappe_order_items ADD COLUMN IF NOT EXISTS balance_due_cents INTEGER NOT NULL DEFAULT 0",
]

_DOWNGRADE = [
    "ALTER TABLE cappe_order_items DROP COLUMN IF EXISTS balance_due_cents",
    "ALTER TABLE cappe_booking_types DROP COLUMN IF EXISTS deposit_cents, DROP COLUMN IF EXISTS payment_mode",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
