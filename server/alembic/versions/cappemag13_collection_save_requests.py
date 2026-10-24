"""Replay-safe saves for editorial collections, including already saved rows.

Revision ID: cappemag13
Revises: cappemag12
Create Date: 2026-10-23
"""
from alembic import op

revision = "cappemag13"
down_revision = "cappemag12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: existing rows and older clients keep working without backfill.
    op.execute("ALTER TABLE cappe_studio_collections ADD COLUMN request_id UUID")
    op.execute("CREATE UNIQUE INDEX idx_cappe_studio_collection_request "
               "ON cappe_studio_collections (account_id, request_id) WHERE request_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX idx_cappe_studio_collection_request")
    op.execute("ALTER TABLE cappe_studio_collections DROP COLUMN request_id")
