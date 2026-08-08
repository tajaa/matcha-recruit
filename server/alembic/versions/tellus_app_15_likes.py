"""tellus_app_15 — consumer likes on board posts, board replies, published
reviews, and reward listings.

Pure counter: no points ledger row, no notification, no earning rule. Four
nullable FK columns (not a polymorphic target_type/target_id pair) so every
target keeps ON DELETE CASCADE — tellus_board_replies is hard-deleted by
routes/board.py:delete_own_reply, and Tell-Us has no orphan-sweep cron to
compensate for a missing FK.

Distinct from tellus_reports.hearted_at/hearted_by (tellus_app_01), which is
the BRAND's one-bit acknowledgment of a review. That column is untouched here.

Revision ID: tellus_app_15
Revises: tellus_app_14
"""
from alembic import op

revision = "tellus_app_15"
down_revision = "tellus_app_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_likes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            post_id    UUID REFERENCES tellus_board_posts(id)     ON DELETE CASCADE,
            reply_id   UUID REFERENCES tellus_board_replies(id)   ON DELETE CASCADE,
            report_id  UUID REFERENCES tellus_reports(id)         ON DELETE CASCADE,
            listing_id UUID REFERENCES tellus_reward_listings(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_likes ADD CONSTRAINT ck_tellus_likes_one_target
                CHECK (num_nonnulls(post_id, reply_id, report_id, listing_id) = 1);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    # One partial unique index per target, ordered (<target>, account_id) — serves
    # count-per-target, did-viewer-like-this, and batch-hydrate-a-page reads, and
    # doubles as the double-tap idempotency guarantee for ON CONFLICT DO NOTHING.
    for col, name in (
        ("post_id", "ux_tellus_likes_post"),
        ("reply_id", "ux_tellus_likes_reply"),
        ("report_id", "ux_tellus_likes_report"),
        ("listing_id", "ux_tellus_likes_listing"),
    ):
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {name} "
            f"ON tellus_likes ({col}, account_id) WHERE {col} IS NOT NULL"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_likes")
