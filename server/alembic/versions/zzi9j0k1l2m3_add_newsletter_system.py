"""Add newsletter system tables (subscribers, newsletters, sends).

Revision ID: zzi9j0k1l2m3
Revises: zzh8i9j0k1l2
Create Date: 2026-04-08
"""
from alembic import op

revision = "zzi9j0k1l2m3"
down_revision = "zzh8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL UNIQUE,
            name VARCHAR(255),
            source VARCHAR(50) DEFAULT 'website',
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
            status VARCHAR(20) DEFAULT 'active',
            subscribed_at TIMESTAMPTZ DEFAULT NOW(),
            unsubscribed_at TIMESTAMPTZ,
            metadata JSONB DEFAULT '{}'::jsonb
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_subscribers_status
        ON newsletter_subscribers(status, subscribed_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_subscribers_source
        ON newsletter_subscribers(source)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS newsletters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(500) NOT NULL,
            subject VARCHAR(500) NOT NULL,
            content_html TEXT,
            curated_article_ids UUID[] DEFAULT '{}',
            status VARCHAR(20) DEFAULT 'draft',
            scheduled_at TIMESTAMPTZ,
            sent_at TIMESTAMPTZ,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletters_status
        ON newsletters(status, created_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_sends (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            newsletter_id UUID NOT NULL REFERENCES newsletters(id) ON DELETE CASCADE,
            subscriber_id UUID NOT NULL REFERENCES newsletter_subscribers(id) ON DELETE CASCADE,
            status VARCHAR(20) DEFAULT 'pending',
            sent_at TIMESTAMPTZ,
            opened_at TIMESTAMPTZ,
            clicked_at TIMESTAMPTZ,
            UNIQUE(newsletter_id, subscriber_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_sends_newsletter
        ON newsletter_sends(newsletter_id, status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS newsletter_sends CASCADE")
    op.execute("DROP TABLE IF EXISTS newsletters CASCADE")
    op.execute("DROP TABLE IF EXISTS newsletter_subscribers CASCADE")
