"""Private sales campaigns and reviewed outreach queue.

Revision ID: mwsales01
Revises: mwcal02
"""

from alembic import op

revision = "mwsales01"
down_revision = "mwcal02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE mw_sales_campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_id UUID NOT NULL,
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL, target TEXT NOT NULL DEFAULT '', offer TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'idle' CHECK(status IN ('idle','sending','paused','complete')),
            sender TEXT, dispatch_token UUID, last_approval_id UUID,
            next_attempt_at TIMESTAMPTZ, error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, request_id)
        )
    """)
    op.execute(
        "CREATE INDEX idx_mw_sales_owner_project ON mw_sales_campaigns(user_id, project_id, updated_at DESC)"
    )
    op.execute("""
        CREATE TABLE mw_sales_prospects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            campaign_id UUID NOT NULL REFERENCES mw_sales_campaigns(id) ON DELETE CASCADE,
            dedupe_key TEXT NOT NULL,
            email TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '',
            website TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', research TEXT NOT NULL DEFAULT '',
            sources JSONB NOT NULL DEFAULT '[]'::jsonb,
            subject TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL DEFAULT 'lead' CHECK(stage IN ('lead','qualified','proposal','negotiation','closed')),
            status TEXT NOT NULL DEFAULT 'prospect' CHECK(status IN ('prospect','draft','approved','claimed','sent','failed','unknown')),
            claimed_at TIMESTAMPTZ, sent_at TIMESTAMPTZ, message_id TEXT, error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(campaign_id, dedupe_key)
        )
    """)
    op.execute(
        "CREATE INDEX idx_mw_sales_queue ON mw_sales_prospects(campaign_id, status, created_at, id)"
    )


def downgrade():
    op.execute("DROP TABLE mw_sales_prospects")
    op.execute("DROP TABLE mw_sales_campaigns")
