"""tellus_app_12 — Regulars board: brand team members, boards, memberships,
posts, pre-moderated replies, board-only listing visibility, board_reply_approved
earning rule.

Also enforces the previously-application-only one-brand-per-account rule with a
partial unique index on tellus_brands.owner_account_id — guarded by a fail-fast
duplicate check (auto-NULLing a duplicate would silently unclaim a brand and
collide with the ensure_community_link invariant + billing; a human resolves).

Revision ID: tellus_app_12
Revises: tellus_app_11
"""
from alembic import op

revision = "tellus_app_12"
down_revision = "tellus_app_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Team table
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'moderator' CHECK (role IN ('owner','moderator')),
            added_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (brand_id, account_id)
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_brand_members_account "
        "ON tellus_brand_members (account_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_brand_members_owner "
        "ON tellus_brand_members (brand_id) WHERE role = 'owner'"
    )

    # 2. Fail-fast guard, then the unique index dependencies.py's LEFT JOIN assumed
    op.execute(
        """DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM tellus_brands WHERE owner_account_id IS NOT NULL
                     GROUP BY owner_account_id HAVING COUNT(*) > 1) THEN
            RAISE EXCEPTION 'tellus_app_12: duplicate tellus_brands.owner_account_id rows — resolve manually before migrating';
          END IF;
        END $$"""
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_brands_owner_unique "
        "ON tellus_brands (owner_account_id) WHERE owner_account_id IS NOT NULL"
    )

    # 3. Backfill owners as owner-members (set-based, idempotent)
    op.execute(
        """INSERT INTO tellus_brand_members (brand_id, account_id, role)
           SELECT id, owner_account_id, 'owner' FROM tellus_brands WHERE owner_account_id IS NOT NULL
           ON CONFLICT (brand_id, account_id) DO NOTHING"""
    )

    # 4. Boards (one per brand; the channel seam)
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_boards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL UNIQUE REFERENCES tellus_brands(id) ON DELETE CASCADE,
            title TEXT,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )

    # 5. Membership queue (claim-queue pattern from tellus_app_10)
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_board_memberships (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            board_id UUID NOT NULL REFERENCES tellus_boards(id) ON DELETE CASCADE,
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','declined','removed','left','cancelled')),
            note TEXT,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMPTZ,
            decided_by UUID REFERENCES tellus_accounts(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_board_memberships_pending "
        "ON tellus_board_memberships (board_id, account_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_board_memberships_approved "
        "ON tellus_board_memberships (board_id, account_id) WHERE status = 'approved'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_board_memberships_board "
        "ON tellus_board_memberships (board_id, status, requested_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_board_memberships_account "
        "ON tellus_board_memberships (account_id, status)"
    )

    # 6. Posts
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_board_posts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            board_id UUID NOT NULL REFERENCES tellus_boards(id) ON DELETE CASCADE,
            channel_id UUID,  -- channel seam: always NULL in v1; FK added when channels land
            author_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            kind TEXT NOT NULL DEFAULT 'update' CHECK (kind IN ('update','deal','event','question')),
            title TEXT NOT NULL,
            body TEXT,
            listing_id UUID REFERENCES tellus_reward_listings(id) ON DELETE SET NULL,
            event_starts_at TIMESTAMPTZ,
            event_ends_at TIMESTAMPTZ,
            is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
            moderation_status TEXT NOT NULL DEFAULT 'visible'
                CHECK (moderation_status IN ('visible','flagged','removed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_board_posts_feed "
        "ON tellus_board_posts (board_id, is_pinned DESC, created_at DESC)"
    )

    # 7. Replies (pre-moderated)
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_board_replies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id UUID NOT NULL REFERENCES tellus_board_posts(id) ON DELETE CASCADE,
            author_account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'held'
                CHECK (status IN ('held','approved','rejected','removed')),
            moderated_at TIMESTAMPTZ,
            moderated_by UUID REFERENCES tellus_accounts(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_board_replies_post "
        "ON tellus_board_replies (post_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_board_replies_held "
        "ON tellus_board_replies (post_id, created_at) WHERE status = 'held'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_board_replies_author "
        "ON tellus_board_replies (author_account_id, created_at DESC)"
    )

    # 8. Listing visibility
    op.execute(
        "ALTER TABLE tellus_reward_listings ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'public'"
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_reward_listings ADD CONSTRAINT ck_tellus_listings_visibility
                CHECK (visibility IN ('public','board'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    # 9. Earning rule (columns verified vs tellus_app_01; event_key UNIQUE)
    op.execute(
        """INSERT INTO tellus_earning_rules (event_key, points, daily_cap, cooldown_seconds, is_active)
           VALUES ('board_reply_approved', 15, 45, NULL, TRUE)
           ON CONFLICT (event_key) DO NOTHING"""
    )


def downgrade() -> None:
    """Content loss is inherent (posts/replies/memberships/boards/team all
    drop). Ledger rows referencing approved replies survive — reference_id is
    a bare TEXT column, no FK — so points history stays intact even though the
    reply it cites is gone."""
    op.execute("DELETE FROM tellus_earning_rules WHERE event_key = 'board_reply_approved'")
    op.execute("ALTER TABLE tellus_reward_listings DROP CONSTRAINT IF EXISTS ck_tellus_listings_visibility")
    op.execute("ALTER TABLE tellus_reward_listings DROP COLUMN IF EXISTS visibility")
    op.execute("DROP TABLE IF EXISTS tellus_board_replies")
    op.execute("DROP TABLE IF EXISTS tellus_board_posts")
    op.execute("DROP TABLE IF EXISTS tellus_board_memberships")
    op.execute("DROP TABLE IF EXISTS tellus_boards")
    op.execute("DROP INDEX IF EXISTS ux_tellus_brands_owner_unique")
    op.execute("DROP TABLE IF EXISTS tellus_brand_members")
