"""Cappe reviews — customer testimonials with creator moderation.

Visitors submit a review (name, 1–5 rating, text) from a published site; it
lands `pending` and only shows once the creator approves it. Surfaced on the
site via the public reviews widget (approved only).

Revision ID: zzzzcappe10
Revises: zzzzcappe09
"""
from alembic import op

revision = "zzzzcappe10"
down_revision = "zzzzcappe09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_reviews (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            author_name VARCHAR(120) NOT NULL,
            rating INTEGER CHECK (rating BETWEEN 1 AND 5),
            body TEXT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'hidden')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_reviews_site_status "
        "ON cappe_reviews(site_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_reviews")
