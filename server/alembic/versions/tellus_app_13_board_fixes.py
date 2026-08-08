"""tellus_app_13 — Regulars board follow-up fixes from PR review.

Two account FKs added in tellus_app_12 (tellus_board_memberships.decided_by,
tellus_board_replies.moderated_by) had no ON DELETE action, unlike every other
account FK in that migration (CASCADE/SET NULL) — deleting an account that ever
decided a join request or moderated a reply would abort with a FK violation.
Fixed to ON DELETE SET NULL (matches author_account_id's pattern on
tellus_board_posts/tellus_board_replies): the decision/moderation record stays,
just anonymized, same as any other "actor account was deleted" case.

Also flips tellus_boards.is_active's column default to FALSE to match
board_service.ensure_board's explicit FALSE insert (a board a GET lazily
creates must not publish the public join CTA until the owner opts in).
Existing board rows are left untouched — this only changes what a bare INSERT
without an explicit is_active gets, and ensure_board already always specifies
it explicitly, so this is belt-and-braces for any other insert path.

Revision ID: tellus_app_13
Revises: tellus_app_12
"""
from alembic import op

revision = "tellus_app_13"
down_revision = "tellus_app_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tellus_board_memberships "
        "DROP CONSTRAINT tellus_board_memberships_decided_by_fkey"
    )
    op.execute(
        "ALTER TABLE tellus_board_memberships "
        "ADD CONSTRAINT tellus_board_memberships_decided_by_fkey "
        "FOREIGN KEY (decided_by) REFERENCES tellus_accounts(id) ON DELETE SET NULL"
    )

    op.execute(
        "ALTER TABLE tellus_board_replies "
        "DROP CONSTRAINT tellus_board_replies_moderated_by_fkey"
    )
    op.execute(
        "ALTER TABLE tellus_board_replies "
        "ADD CONSTRAINT tellus_board_replies_moderated_by_fkey "
        "FOREIGN KEY (moderated_by) REFERENCES tellus_accounts(id) ON DELETE SET NULL"
    )

    op.execute("ALTER TABLE tellus_boards ALTER COLUMN is_active SET DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE tellus_boards ALTER COLUMN is_active SET DEFAULT TRUE")

    op.execute(
        "ALTER TABLE tellus_board_replies "
        "DROP CONSTRAINT tellus_board_replies_moderated_by_fkey"
    )
    op.execute(
        "ALTER TABLE tellus_board_replies "
        "ADD CONSTRAINT tellus_board_replies_moderated_by_fkey "
        "FOREIGN KEY (moderated_by) REFERENCES tellus_accounts(id)"
    )

    op.execute(
        "ALTER TABLE tellus_board_memberships "
        "DROP CONSTRAINT tellus_board_memberships_decided_by_fkey"
    )
    op.execute(
        "ALTER TABLE tellus_board_memberships "
        "ADD CONSTRAINT tellus_board_memberships_decided_by_fkey "
        "FOREIGN KEY (decided_by) REFERENCES tellus_accounts(id)"
    )
