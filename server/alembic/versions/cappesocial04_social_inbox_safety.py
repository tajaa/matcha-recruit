"""Cappe — social inbox safety (the 2026-10-27 Instagram automation audit).

`cappe_social_connections.inbox_enabled` — whether this account's comments
and DMs reach the site's inbox (and so its AI replies). Connect brings in
every Page the person manages; one that isn't the store's must not be
answered as the store. Existing rows keep today's behaviour (true); a new
Connect that returns more than one Page leaves them off until the owner
turns on the ones that are the store's.

Indexes for the lookups the inbound worker and the sweep now make: a sent
reply by its network id (our own reply coming back as a webhook is dropped),
`new` items by time, and an item by its network id across sites.

`scheduler_settings` rows:
  * `cappe_social_inbox_sweep` (seeded ON) — the hourly retry for comments
    and DMs the reply policy couldn't get to (the model unavailable or at its
    cap, a worker that died after storing them). Without it they stay `new`
    for good.
  * `cappe_social_metrics` turned ON — besides followers and reach, it is the
    hourly check that catches a token Meta no longer accepts (a former Page
    admin's), which takes that connection out of the inbox fan-out.

Additive + idempotent; the downgrade drops the column, the indexes and the
sweep row and turns metrics back off.

Revision ID: cappesocial04
Revises: cappeboard01
"""
from alembic import op

revision = "cappesocial04"
down_revision = "cappeboard01"
branch_labels = None
depends_on = None

_UPGRADE = [
    "ALTER TABLE cappe_social_connections ADD COLUMN IF NOT EXISTS inbox_enabled BOOLEAN NOT NULL DEFAULT true",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_replies_external "
    "ON cappe_social_replies (external_reply_id) WHERE external_reply_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_inbox_new ON cappe_social_inbox (received_at) WHERE status = 'new'",
    "CREATE INDEX IF NOT EXISTS idx_cappe_social_inbox_external ON cappe_social_inbox (external_id)",
    """
    INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
    VALUES ('cappe_social_inbox_sweep', 'Cappe Social Inbox Sweep',
            'Retry the reply policy on social comments and messages it could not get to (hourly).', true, 50)
    ON CONFLICT (task_key) DO NOTHING
    """,
    """
    UPDATE scheduler_settings
       SET enabled = true,
           description = 'Refresh follower counts and per-post reach, and mark accounts whose token Meta '
                         'no longer accepts (hourly).'
     WHERE task_key = 'cappe_social_metrics'
    """,
]

_DOWNGRADE = [
    """
    UPDATE scheduler_settings
       SET enabled = false,
           description = 'Refresh follower counts and per-post reach for connected social accounts.'
     WHERE task_key = 'cappe_social_metrics'
    """,
    "DELETE FROM scheduler_settings WHERE task_key = 'cappe_social_inbox_sweep'",
    "DROP INDEX IF EXISTS idx_cappe_social_inbox_external",
    "DROP INDEX IF EXISTS idx_cappe_social_inbox_new",
    "DROP INDEX IF EXISTS idx_cappe_social_replies_external",
    "ALTER TABLE cappe_social_connections DROP COLUMN IF EXISTS inbox_enabled",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
