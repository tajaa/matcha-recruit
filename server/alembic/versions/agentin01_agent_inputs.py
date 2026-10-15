"""Espresso: files a person gives the assistant, kept in private storage.

Revision ID: agentin01
Revises: mwjobs01

A file dropped into a private conversation with Espresso (a résumé, a photo,
a spreadsheet) used to go to the public CDN through the ordinary channel
upload, and never reached the assistant. Now it is stored in the private
bucket (`storage_path` is always an `s3://` URI) and recorded here, with the
text extracted once at upload so a run can read it without fetching the file.

Messages carry the file as an `espresso-input:<id>` attachment URL; the app
asks for a short-lived link to show it. `seen_run_id` is the first run that
was given the file, so a file sent on its own reaches the next request.

The downgrade drops the table. The stored objects stay in the bucket.
"""
from alembic import op

revision = "agentin01"
down_revision = "mwjobs01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE mw_agent_inputs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('document', 'image')),
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            sha256 TEXT NOT NULL,
            storage_path TEXT NOT NULL CHECK (storage_path LIKE 's3://%'),
            text_excerpt TEXT,
            extract_status TEXT NOT NULL DEFAULT 'skipped'
                CHECK (extract_status IN ('ok', 'empty', 'failed', 'skipped')),
            seen_run_id UUID REFERENCES mw_project_agent_runs(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_mw_agent_inputs_user ON mw_agent_inputs (user_id, created_at DESC)")
    op.execute("""
        CREATE INDEX idx_mw_agent_inputs_channel ON mw_agent_inputs (channel_id, created_at DESC)
        WHERE channel_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_mw_agent_inputs_message ON mw_agent_inputs (message_id)
        WHERE message_id IS NOT NULL
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_agent_inputs")
