"""cappe: matcha feature bridge (parallel entitlement)

Lets a Cappe (gummfit) account hold matcha features without merging the two
identity models:

- `matcha_features` JSONB — the cappe-side entitlement flags (broker-style
  parallel entitlement; whitelist enforced in
  `app/cappe/services/matcha_bridge.py`, NOT matcha's feature_flags.py).
- `matcha_company_id` / `matcha_user_id` — the "backing tenant": one minimal
  companies row + one unloginable users/clients pair created lazily on first
  enable. Pure data-layer plumbing so matcha's ir_* FK constraints + RLS are
  satisfied; the backing user can never authenticate (random discarded
  password, bridge email on a reserved .invalid domain) and gating stays
  entirely cappe-side (scope=cappe tokens are still rejected by matcha).

Additive; no existing table touched.

Revision ID: cappebridge01
Revises: zzzzcappe21
Create Date: 2026-07-13
"""
from alembic import op

revision = "cappebridge01"
down_revision = "zzzzcappe21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_accounts
            ADD COLUMN IF NOT EXISTS matcha_features JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS matcha_company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS matcha_user_id UUID REFERENCES users(id) ON DELETE SET NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_accounts_matcha_company "
        "ON cappe_accounts(matcha_company_id) WHERE matcha_company_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_accounts_matcha_company")
    op.execute(
        """
        ALTER TABLE cappe_accounts
            DROP COLUMN IF EXISTS matcha_features,
            DROP COLUMN IF EXISTS matcha_company_id,
            DROP COLUMN IF EXISTS matcha_user_id
        """
    )
