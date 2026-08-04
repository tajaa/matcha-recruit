"""Tell-Us — public reviews (48h hold) + brand<->reviewer DMs.

Some feedback can now be posted as a public review instead of staying private
brand-only feedback. `review_state IS NULL` means the row is still ordinary
private feedback; `review_state = 'held'` + `publish_at` means it's a review
serving a fixed 48-hour hold before it appears on the brand's public page.

Deliberately NOT storing a `'published'` state: publication is lazy (derived
at read time as `review_state = 'held' AND publish_at <= NOW()`), so there is
no write-time event to set it at — no cron, no worker. Storing a third state
that nothing ever transitions into would just be a value the code could drift
out of sync with reality. `(review_state IS NULL) = (publish_at IS NULL)`
keeps the two paired so a review always has its clock and private feedback
never grows one by accident.

Also adds `tellus_brands.slug` (public URL: /tellus/b/{slug}) and the DM
thread/message tables backing brand-initiated conversations with an
identified reviewer.

Revision ID: tellus_app_05
Revises: tellus_app_04
Create Date: 2026-08-04
"""
from alembic import op


revision = "tellus_app_05"
down_revision = "tellus_app_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tellus_reports: rating + review hold + heart + public reply ────────
    op.execute("ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS rating SMALLINT")
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_reports ADD CONSTRAINT ck_tellus_reports_rating
                CHECK (rating IS NULL OR rating BETWEEN 1 AND 5);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    op.execute("ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS review_state TEXT")
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_reports ADD CONSTRAINT ck_tellus_reports_review_state
                CHECK (review_state IS NULL OR review_state IN ('held', 'withdrawn'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    op.execute("ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS publish_at TIMESTAMPTZ")
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_reports ADD CONSTRAINT ck_tellus_reports_review_pair
                CHECK ((review_state IS NULL) = (publish_at IS NULL));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    op.execute("ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS hearted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS hearted_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL")

    op.execute("ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS brand_public_reply TEXT")
    op.execute("ALTER TABLE tellus_reports ADD COLUMN IF NOT EXISTS brand_public_reply_at TIMESTAMPTZ")

    # Brand's public review page: newest-first, hold-aware (partial index —
    # withdrawn/private rows never qualify so they're excluded at the index
    # level, not filtered post-hoc).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_reports_public "
        "ON tellus_reports (brand_id, publish_at DESC) WHERE review_state = 'held'"
    )

    # ── tellus_brands.slug — set-based, collision-safe backfill ────────────
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS slug TEXT")

    # Pass 1: slugify the name, dedupe first-order collisions by appending the
    # 1-based rank within each base slug (deterministic ORDER BY id). Capped
    # at 60 chars — must mirror routes/_shared.py:slugify()'s order of
    # operations (strip specials -> trim both ends -> cut -> trim the
    # trailing dash a mid-cut can leave) or new signups and backfilled rows
    # would slug differently for the same name.
    op.execute(
        """
        WITH base AS (
            SELECT id,
                   COALESCE(NULLIF(trim(trailing '-' FROM left(trim(both '-' FROM
                       regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g')), 60)), ''), 'brand') AS base_slug
            FROM tellus_brands
            WHERE slug IS NULL
        ), numbered AS (
            SELECT id, base_slug, ROW_NUMBER() OVER (PARTITION BY base_slug ORDER BY id) AS rn
            FROM base
        )
        UPDATE tellus_brands b
        SET slug = CASE WHEN n.rn = 1 THEN n.base_slug ELSE n.base_slug || '-' || n.rn END
        FROM numbered n
        WHERE b.id = n.id
        """
    )

    # Pass 2: second-order collisions (e.g. "Acme 2" the name vs "Acme"'s
    # generated "-2" suffix landing on the same slug) — append a slice of the
    # row's own UUID to every non-first duplicate. One pass is enough since
    # a UUID slice can't collide with itself.
    op.execute(
        """
        WITH dups AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY slug ORDER BY id) AS rn
            FROM tellus_brands
        )
        UPDATE tellus_brands b
        SET slug = b.slug || '-' || left(b.id::text, 8)
        FROM dups d
        WHERE b.id = d.id AND d.rn > 1
        """
    )

    op.execute("ALTER TABLE tellus_brands ALTER COLUMN slug SET NOT NULL")
    # Terminal assert: if backfill left any duplicate, this fails and the
    # whole revision rolls back under rehearsal rather than half-applying.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_brands_slug ON tellus_brands (slug)")

    # ── DM threads (one per report) + messages ─────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_dm_threads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_id UUID NOT NULL UNIQUE REFERENCES tellus_reports(id) ON DELETE CASCADE,
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            consumer_account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            blocked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_dm_threads_brand ON tellus_dm_threads (brand_id, last_message_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_dm_threads_consumer ON tellus_dm_threads (consumer_account_id, last_message_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_dm_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES tellus_dm_threads(id) ON DELETE CASCADE,
            sender_role TEXT NOT NULL CHECK (sender_role IN ('brand', 'consumer')),
            sender_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            body TEXT NOT NULL,
            read_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_dm_messages_thread ON tellus_dm_messages (thread_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_dm_messages")
    op.execute("DROP TABLE IF EXISTS tellus_dm_threads")

    op.execute("DROP INDEX IF EXISTS ux_tellus_brands_slug")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS slug")

    op.execute("DROP INDEX IF EXISTS ix_tellus_reports_public")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS brand_public_reply_at")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS brand_public_reply")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS hearted_by")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS hearted_at")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS publish_at")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS review_state")
    op.execute("ALTER TABLE tellus_reports DROP COLUMN IF EXISTS rating")
