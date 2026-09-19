"""Cappe: durable record of CloudFront tenants whose domain row is gone.

Deleting a site cascades its `cappe_domains` rows away, and with them the only
record of each domain's CloudFront distribution tenant. The cleanup used to be a
single in-process attempt after the response: CloudFront refuses to delete a
tenant that is still deploying its `Enabled=false` change, and a blue/green swap
kills the task outright — either way the id was lost, the orphaned tenant kept
billing, and reconnecting the domain failed with "already exists".

`cappe_edge_tombstones` is written in the same transaction as the site delete
and drained by the `cappe_edge_sync` sweeper, which retries until CloudFront
confirms the tenant is gone.

Revision ID: zzzzcappe32
Revises: zzzzcappe31
Create Date: 2026-09-18
"""
from alembic import op

revision = "zzzzcappe32"
down_revision = "zzzzcappe31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS cappe_edge_tombstones (
            cf_tenant_id TEXT PRIMARY KEY,
            domain TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            checked_at TIMESTAMPTZ
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_edge_tombstones")
