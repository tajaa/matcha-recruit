"""Cappe magazines — readers follow magazines from their Gummfit account.

A follow is one row per (account, magazine site): a signed-in reader's
one-tap Follow on their dashboard. It sends no email; the magazine's email
followers stay `cappe_subscribers` (double opt-in, unchanged). The dashboard
reads these rows for its Following list and its feed of new stories, and the
owner sees only how many there are.

Both keys cascade: deleting an account or a site drops its follows.

Revision ID: cappemag08
Revises: cappemag07
Create Date: 2026-10-22
"""
from alembic import op

revision = "cappemag08"
down_revision = "cappemag07"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_magazine_follows (
        account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (account_id, site_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_magazine_follows_site ON cappe_magazine_follows (site_id)",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_magazine_follows")
