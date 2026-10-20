"""Cappe — signup grants: a link that gives a new account a paid plan for a while.

A Matcha admin makes a grant at /admin/cappe ("30 days of Business"), sends
its link, and whoever signs up through it gets that plan as a comp once they
confirm their email: no card, no checkout. The comp carries `comped_until`, and
`cappe_comp_expiry` drops the account back to free when it runs out, so after
that they pay like everybody else.

`cappe_signup_grants`
  * `token` — the secret in the link (`/cappe/signup?grant=<token>`).
  * `plan_code` / `days` — what it gives, and for how long from confirmation.
  * `max_redemptions` / `redeemed_count` — how many accounts it may start.
  * `email` — when set, only that address can use it.
  * `expires_at` — the link stops working after this; `revoked_at` ends it now.

`cappe_accounts.signup_grant_id` — the grant an account signed up with, kept
from signup until the email is confirmed. `signup_grant_redeemed_at` — when the
comp was given; `signup_grant_refused` — why it wasn't (used up, revoked, the
account already had a plan). One of the two is set once, which is what stops
a grant being looked at twice.

Also turns ON the `cappe_comp_expiry` sweep (seeded off in zzzzcappe26). Every
comp from these links ends because of it; with it off, a 30-day grant is a
free plan forever. It has never run on prod and no comp exists there, so
turning it on changes nothing for anyone today. The downgrade leaves it as is.

Additive + idempotent. The downgrade drops the table and both columns.

Revision ID: zzzzcappe48
Revises: mwjobs04
"""
from alembic import op

revision = "zzzzcappe48"
down_revision = "mwjobs04"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_signup_grants (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        token VARCHAR(64) NOT NULL UNIQUE,
        plan_code VARCHAR(40) NOT NULL REFERENCES cappe_billing_products(code),
        days INTEGER NOT NULL CHECK (days BETWEEN 1 AND 366),
        max_redemptions INTEGER NOT NULL DEFAULT 1 CHECK (max_redemptions BETWEEN 1 AND 1000),
        redeemed_count INTEGER NOT NULL DEFAULT 0,
        email VARCHAR(320),
        note TEXT,
        expires_at TIMESTAMPTZ,
        revoked_at TIMESTAMPTZ,
        created_by_email VARCHAR(320),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT cappe_signup_grants_count
            CHECK (redeemed_count >= 0 AND redeemed_count <= max_redemptions)
    )
    """,
    """
    ALTER TABLE cappe_accounts
        ADD COLUMN IF NOT EXISTS signup_grant_id UUID
            REFERENCES cappe_signup_grants(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS signup_grant_redeemed_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS signup_grant_refused TEXT
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_accounts_signup_grant ON cappe_accounts (signup_grant_id) "
    "WHERE signup_grant_id IS NOT NULL",
    "UPDATE scheduler_settings SET enabled = true WHERE task_key = 'cappe_comp_expiry'",
]

_DOWNGRADE = [
    "DROP INDEX IF EXISTS idx_cappe_accounts_signup_grant",
    """
    ALTER TABLE cappe_accounts
        DROP COLUMN IF EXISTS signup_grant_refused,
        DROP COLUMN IF EXISTS signup_grant_redeemed_at,
        DROP COLUMN IF EXISTS signup_grant_id
    """,
    "DROP TABLE IF EXISTS cappe_signup_grants",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
