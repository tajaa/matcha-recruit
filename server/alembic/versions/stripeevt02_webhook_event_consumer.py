"""stripe_webhook_events: scope the dedupe key by consumer

Matcha core and Cappe share ONE Stripe platform account and one secret key
(`settings.stripe_secret_key` — see the CappeStripe docstring). Core's webhook
already handles `invoice.payment_failed`, `invoice.paid` and
`customer.subscription.deleted` (`core/routes/billing/stripe_webhook.py:721,
738,804`) — precisely the events a Cappe subscription product needs.

`event_id` was a GLOBAL primary key. So the moment a second endpoint subscribes
to those same event types, both endpoints receive the identical `evt_...` and
whichever calls `_claim_event` first wins; the other sees a conflict, reads it
as "already processed", and silently skips every side effect. Nothing raises
and nothing logs an error — a Matcha subscription simply never activates, or a
Cappe one doesn't, depending on delivery order.

Scoping the key by consumer makes the endpoints independent. Existing rows
default to 'core', so core's behaviour is byte-identical after this runs.

Known consumers: 'core', 'cappe_platform', 'cappe_connect'.

Revision ID: stripeevt02
Revises: zzzzcappe25
Create Date: 2026-07-30
"""
from alembic import op

revision = "stripeevt02"
down_revision = "zzzzcappe25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stripe_webhook_events "
        "ADD COLUMN IF NOT EXISTS consumer VARCHAR(40) NOT NULL DEFAULT 'core'"
    )
    op.execute("ALTER TABLE stripe_webhook_events DROP CONSTRAINT IF EXISTS stripe_webhook_events_pkey")
    op.execute("ALTER TABLE stripe_webhook_events ADD PRIMARY KEY (consumer, event_id)")


def downgrade() -> None:
    # Restoring a single-column PK requires collapsing any event_id that was
    # legitimately claimed by more than one consumer. Prefer keeping the 'core'
    # row (it is the one whose absence would break existing behaviour), then
    # dedupe whatever remains by ctid — set-based, per the repo's migration rules.
    op.execute(
        """
        DELETE FROM stripe_webhook_events a
         USING stripe_webhook_events b
         WHERE a.event_id = b.event_id
           AND a.consumer <> 'core'
           AND b.consumer = 'core'
        """
    )
    op.execute(
        """
        DELETE FROM stripe_webhook_events a
         USING stripe_webhook_events b
         WHERE a.event_id = b.event_id
           AND a.ctid > b.ctid
        """
    )
    op.execute("ALTER TABLE stripe_webhook_events DROP CONSTRAINT IF EXISTS stripe_webhook_events_pkey")
    op.execute("ALTER TABLE stripe_webhook_events ADD PRIMARY KEY (event_id)")
    op.execute("ALTER TABLE stripe_webhook_events DROP COLUMN IF EXISTS consumer")
