"""Cappe magazines — reader accounts.

A reader is someone who subscribes to magazines and sells nothing. Their
Gummfit login (`account_type='reader'`) gathers every magazine they hold into
one dashboard. On each magazine they are still that site's `cappe_shoppers`
row, matched by the account's confirmed email, so no new table is needed:

  * `cappe_accounts.account_type` gains `reader`;
  * `cappe_shoppers` gets an index on `email`, because the dashboard looks a
    reader up across every site (the unique key starts with `site_id`).

The downgrade refuses while any reader account exists.

Revision ID: cappemag06
Revises: cappemag05
Create Date: 2026-10-21
"""
from alembic import op

revision = "cappemag06"
down_revision = "cappemag05"
branch_labels = None
depends_on = None

_UPGRADE = [
    "ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS cappe_accounts_account_type_check",
    "ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_account_type_check "
    "CHECK (account_type IN ('business', 'personal', 'creator', 'writer', 'reader'))",
    "CREATE INDEX IF NOT EXISTS idx_cappe_shoppers_email ON cappe_shoppers (email)",
]

_DOWNGRADE = [
    """
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM cappe_accounts WHERE account_type = 'reader') THEN
            RAISE EXCEPTION 'cappemag06 downgrade: reader accounts exist';
        END IF;
    END $$
    """,
    "DROP INDEX IF EXISTS idx_cappe_shoppers_email",
    "ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS cappe_accounts_account_type_check",
    "ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_account_type_check "
    "CHECK (account_type IN ('business', 'personal', 'creator', 'writer'))",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
