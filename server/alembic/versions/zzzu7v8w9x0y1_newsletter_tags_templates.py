"""newsletter P1+P2 — tags, subscriber_tags, templates

P1 introduces tags so admin can target Free vs Lite vs Personal segments
(or content-bucket segments like blog/calculators). P2 introduces saved
templates so admin can spin up new newsletters from a known baseline.

Revision ID: zzzu7v8w9x0y1
Revises: zzzt6u7v8w9x0
Create Date: 2026-05-03
"""

from alembic import op


revision = "zzzu7v8w9x0y1"
down_revision = "zzzt6u7v8w9x0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tags — slug is the public/auto-tag identifier ('blog', 'tag-tier-free').
    op.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_tags (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug VARCHAR(64) NOT NULL UNIQUE,
            label VARCHAR(120) NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_subscriber_tags (
            subscriber_id UUID NOT NULL REFERENCES newsletter_subscribers(id) ON DELETE CASCADE,
            tag_id UUID NOT NULL REFERENCES newsletter_tags(id) ON DELETE CASCADE,
            attached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (subscriber_id, tag_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_subscriber_tags_tag
            ON newsletter_subscriber_tags(tag_id)
    """)

    # Saved templates (P2). content_html sanitized at write time.
    op.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            content_html TEXT,
            preheader VARCHAR(255),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Seed the four tier tags so the auto-tag-on-subscribe path finds them
    # without needing the admin to pre-create rows.
    op.execute("""
        INSERT INTO newsletter_tags (slug, label, description) VALUES
            ('tier-free', 'Free tier', 'Subscribers who signed up while logged in as a resources_free customer'),
            ('tier-lite', 'Matcha Lite', 'Subscribers from Matcha Lite tenants'),
            ('tier-platform', 'Platform', 'Subscribers from bespoke / platform tenants'),
            ('tier-personal', 'Matcha Work Personal', 'Personal-workspace individuals')
        ON CONFLICT (slug) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS newsletter_templates")
    op.execute("DROP INDEX IF EXISTS idx_newsletter_subscriber_tags_tag")
    op.execute("DROP TABLE IF EXISTS newsletter_subscriber_tags")
    op.execute("DROP TABLE IF EXISTS newsletter_tags")
