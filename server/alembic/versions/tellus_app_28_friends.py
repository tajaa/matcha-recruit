"""tellus_app_28 — friends: mutual friendship edges, request queue, @handles,
profile visibility, account-level blocks, abuse reports, invite tokens.

Friendship is stored as two mirrored rows, not one canonical (lo,hi) row: the
friend activity feed and every is_friend check then resolve through a single
composite-PK lookup instead of an OR-predicate or a UNION. The symmetry
invariant is enforced in exactly one writer and one deleter
(services/friends_service.py) and pinned by a source-guard test.

citext is deliberately NOT installed (this repo has never run CREATE
EXTENSION outside `vector` — see zzzzcappe25_directory's note); case-
insensitive handle uniqueness is a unique index on lower(handle), and handles
are stored already-lowercased by the Pydantic validator so the two can never
disagree. Search is prefix-only for the same reason (no pg_trgm) — see
services/friends_service.py.

Revision ID: tellus_app_28
Revises: tellus_app_27
"""
from alembic import op


revision = "tellus_app_28"
down_revision = "tellus_app_27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tellus_accounts additions ───────────────────────────────────────────
    op.execute("ALTER TABLE tellus_accounts ADD COLUMN IF NOT EXISTS handle TEXT")
    op.execute("ALTER TABLE tellus_accounts ADD COLUMN IF NOT EXISTS handle_set_at TIMESTAMPTZ")
    op.execute("ALTER TABLE tellus_accounts ADD COLUMN IF NOT EXISTS avatar_url TEXT")
    op.execute(
        "ALTER TABLE tellus_accounts ADD COLUMN IF NOT EXISTS profile_visibility "
        "TEXT NOT NULL DEFAULT 'friends'"
    )
    op.execute(
        "ALTER TABLE tellus_accounts ADD COLUMN IF NOT EXISTS discoverable "
        "BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_accounts ADD CONSTRAINT ck_tellus_accounts_profile_visibility
                CHECK (profile_visibility IN ('everyone', 'friends', 'private'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_accounts ADD CONSTRAINT ck_tellus_accounts_handle_format
                CHECK (handle IS NULL OR handle ~ '^[a-z0-9_]{3,20}$');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    # WHY: case-insensitive uniqueness (no citext). Also the exact-handle
    # lookup behind GET /people/by-handle/{handle} and a handle-based request.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_accounts_handle_lower "
        "ON tellus_accounts (lower(handle)) WHERE handle IS NOT NULL"
    )
    # WHY: GET /friends/search's `handle LIKE 'q%'`. A default-collation
    # btree cannot serve LIKE prefix matching unless the DB is C-locale;
    # text_pattern_ops makes the prefix scan work regardless of lc_collate.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_accounts_handle_prefix "
        "ON tellus_accounts (handle text_pattern_ops) WHERE handle IS NOT NULL"
    )
    # WHY: the second OR-branch of the same search
    # (`lower(display_name) LIKE 'q%'`). display_name is non-unique and
    # nullable; without this the search is a seq scan of tellus_accounts.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_accounts_display_name_prefix "
        "ON tellus_accounts (lower(display_name) text_pattern_ops) "
        "WHERE display_name IS NOT NULL AND account_type = 'consumer'"
    )
    # WHY: the same-city suggestion source.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_accounts_city_consumer "
        "ON tellus_accounts (lower(city)) WHERE account_type = 'consumer'"
    )

    # ── tellus_friendships (mirrored edges) ─────────────────────────────────
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_friendships (
               account_id        UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               friend_account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               source            TEXT NOT NULL DEFAULT 'request'
                                 CHECK (source IN ('request', 'invite_link', 'suggestion')),
               created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               PRIMARY KEY (account_id, friend_account_id),
               CONSTRAINT ck_tellus_friendships_not_self CHECK (account_id <> friend_account_id)
           )"""
    )
    # WHY: "my friends, newest first" (GET /me/friends) and the friend-id
    # array the feed builds. Mirrors ix_tellus_brand_follows_consumer_created.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_friendships_account_created "
        "ON tellus_friendships (account_id, created_at DESC)"
    )
    # WHY: the reverse hop of friends-of-friends suggestions. The PK only
    # covers the forward direction.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_friendships_friend "
        "ON tellus_friendships (friend_account_id)"
    )

    # ── tellus_friend_requests ───────────────────────────────────────────────
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_friend_requests (
               id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
               requester_account_id  UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               addressee_account_id  UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               status                TEXT NOT NULL DEFAULT 'pending'
                                     CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled')),
               source                TEXT NOT NULL DEFAULT 'search'
                                     CHECK (source IN ('search', 'handle', 'suggestion', 'profile', 'invite_link')),
               created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               decided_at            TIMESTAMPTZ,
               pair_lo UUID GENERATED ALWAYS AS (
                   CASE WHEN requester_account_id < addressee_account_id
                        THEN requester_account_id ELSE addressee_account_id END) STORED,
               pair_hi UUID GENERATED ALWAYS AS (
                   CASE WHEN requester_account_id < addressee_account_id
                        THEN addressee_account_id ELSE requester_account_id END) STORED,
               CONSTRAINT ck_tellus_friend_requests_not_self
                   CHECK (requester_account_id <> addressee_account_id)
           )"""
    )
    # WHY: at most ONE live request per pair in EITHER direction. Direction-
    # scoped uniqueness alone would let A->B and B->A both sit pending. This
    # is the race backstop; the service pre-checks and auto-accepts a
    # reciprocal pending request before ever hitting it (mutual intent =
    # friends).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_friend_requests_pending "
        "ON tellus_friend_requests (pair_lo, pair_hi) WHERE status = 'pending'"
    )
    # WHY: GET /me/friend-requests?direction=incoming + the unread badge count.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_friend_requests_addressee "
        "ON tellus_friend_requests (addressee_account_id, status, created_at DESC)"
    )
    # WHY: GET /me/friend-requests?direction=outgoing.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_friend_requests_requester "
        "ON tellus_friend_requests (requester_account_id, status, created_at DESC)"
    )
    # WHY: the decline-cooldown lookup — "latest row of any status for this pair".
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_friend_requests_pair_recent "
        "ON tellus_friend_requests (pair_lo, pair_hi, created_at DESC)"
    )

    # ── tellus_account_blocks ────────────────────────────────────────────────
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_account_blocks (
               blocker_account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               blocked_account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               PRIMARY KEY (blocker_account_id, blocked_account_id),
               CONSTRAINT ck_tellus_account_blocks_not_self
                   CHECK (blocker_account_id <> blocked_account_id)
           )"""
    )
    # WHY: blocks are stored asymmetrically but ENFORCED symmetrically — every
    # read path asks "did they block me?", which the PK cannot serve.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_account_blocks_blocked "
        "ON tellus_account_blocks (blocked_account_id)"
    )

    # ── tellus_abuse_reports (NOT tellus_reports — that table means reviews) ─
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_abuse_reports (
               id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
               reporter_account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               subject_account_id  UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               target_type         TEXT NOT NULL DEFAULT 'account'
                                   CHECK (target_type IN ('account', 'review', 'board_reply')),
               target_id           UUID,
               reason              TEXT NOT NULL
                                   CHECK (reason IN ('spam', 'harassment', 'impersonation', 'inappropriate', 'other')),
               detail              TEXT,
               status              TEXT NOT NULL DEFAULT 'open'
                                   CHECK (status IN ('open', 'reviewing', 'actioned', 'dismissed')),
               resolution_note     TEXT,
               resolved_at         TIMESTAMPTZ,
               resolved_by         UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
               created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               CONSTRAINT ck_tellus_abuse_reports_not_self
                   CHECK (reporter_account_id <> subject_account_id)
           )"""
    )
    # WHY: the admin queue's default read (open reports, newest first).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_abuse_reports_queue "
        "ON tellus_abuse_reports (status, created_at DESC)"
    )
    # WHY: admin triage "how many reports stand against this account".
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_abuse_reports_subject "
        "ON tellus_abuse_reports (subject_account_id, created_at DESC)"
    )
    # WHY: one OPEN report per reporter per subject — the anti-spam property.
    # Deliberately NOT keyed on target_id: nullable columns compare distinct
    # under UNIQUE, so a target-keyed index would let one reporter file
    # unlimited account-level (target_id IS NULL) reports.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_abuse_reports_open "
        "ON tellus_abuse_reports (reporter_account_id, subject_account_id) "
        "WHERE status IN ('open', 'reviewing')"
    )

    # ── tellus_friend_invites ─────────────────────────────────────────────────
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_friend_invites (
               id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
               account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
               token      TEXT NOT NULL UNIQUE,
               max_uses   INTEGER,
               use_count  INTEGER NOT NULL DEFAULT 0,
               expires_at TIMESTAMPTZ,
               revoked_at TIMESTAMPTZ,
               created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
           )"""
    )
    # WHY: exactly one live token per account. GET /me/friend-invite is
    # mint-or-return, and rotate must not leave two valid QR codes in the wild.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_friend_invites_active "
        "ON tellus_friend_invites (account_id) WHERE revoked_at IS NULL"
    )

    # ── author-scoped review index (the friend feed / profile reviews list) ──
    # WHY: the friend profile's "their published reviews" and the review
    # branch of the activity feed both scan by author ORDER BY publish_at
    # DESC. The existing ix_tellus_reports_public is (brand_id, publish_at
    # DESC) — brand-scoped, wrong leading column. ix_tellus_reports_reporter
    # is (reporter_account_id) with no sort key and no partial predicate, so
    # it degenerates to a heap fetch + sort. publish_at <= NOW() cannot live
    # in the predicate (not immutable) and stays in the WHERE clause.
    #
    # No new index is added on tellus_brand_follows —
    # ix_tellus_brand_follows_consumer_created (tellus_app_18) is already the
    # exact shape the feed's follow branch wants.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_reports_author_published "
        "ON tellus_reports (reporter_account_id, publish_at DESC) "
        "WHERE review_state = 'held' AND moderation_status = 'visible'"
    )

    # ── earning rule seed ─────────────────────────────────────────────────────
    op.execute(
        """INSERT INTO tellus_earning_rules (event_key, points, daily_cap, cooldown_seconds, is_active)
           VALUES ('friend_added', 10, 50, NULL, TRUE)
           ON CONFLICT (event_key) DO NOTHING"""
    )


def downgrade() -> None:
    """Content loss is inherent (friendships, requests, blocks, abuse reports,
    invite tokens all drop). Ledger rows citing 'friendship' reference_ids
    survive — reference_id is a bare TEXT column with no FK — so points
    history stays intact. Handles are dropped, which frees every claimed
    name; a re-upgrade cannot restore who had which."""
    op.execute("DELETE FROM tellus_earning_rules WHERE event_key = 'friend_added'")
    op.execute("DROP INDEX IF EXISTS ix_tellus_reports_author_published")
    op.execute("DROP TABLE IF EXISTS tellus_friend_invites")
    op.execute("DROP TABLE IF EXISTS tellus_abuse_reports")
    op.execute("DROP TABLE IF EXISTS tellus_account_blocks")
    op.execute("DROP TABLE IF EXISTS tellus_friend_requests")
    op.execute("DROP TABLE IF EXISTS tellus_friendships")
    op.execute("DROP INDEX IF EXISTS ix_tellus_accounts_city_consumer")
    op.execute("DROP INDEX IF EXISTS ix_tellus_accounts_display_name_prefix")
    op.execute("DROP INDEX IF EXISTS ix_tellus_accounts_handle_prefix")
    op.execute("DROP INDEX IF EXISTS ux_tellus_accounts_handle_lower")
    op.execute("ALTER TABLE tellus_accounts DROP CONSTRAINT IF EXISTS ck_tellus_accounts_handle_format")
    op.execute("ALTER TABLE tellus_accounts DROP CONSTRAINT IF EXISTS ck_tellus_accounts_profile_visibility")
    op.execute("ALTER TABLE tellus_accounts DROP COLUMN IF EXISTS discoverable")
    op.execute("ALTER TABLE tellus_accounts DROP COLUMN IF EXISTS profile_visibility")
    op.execute("ALTER TABLE tellus_accounts DROP COLUMN IF EXISTS avatar_url")
    op.execute("ALTER TABLE tellus_accounts DROP COLUMN IF EXISTS handle_set_at")
    op.execute("ALTER TABLE tellus_accounts DROP COLUMN IF EXISTS handle")
