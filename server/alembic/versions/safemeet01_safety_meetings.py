"""safety_meetings: AI-transcribed safety meeting (toolbox talk) records.

One table holds the whole lifecycle recording -> review -> signed. Transcript
segments arrive as ~1-minute audio chunks while the meeting runs (each with its
private-bucket audio path); "finish" assembles the full transcript and a
Gemini-written summary the safety manager edits before sign-off. Signed rows
are the durable compliance artifact — editing is refused once signed.
"""

from alembic import op


revision = "safemeet01"
down_revision = "sales01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS safety_meetings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            title VARCHAR(200) NOT NULL,
            topic TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'recording'
                CHECK (status IN ('recording', 'review', 'signed')),
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMPTZ,
            -- [{idx, text, audio_path}] ordered by idx; audio_path is the
            -- private-bucket s3:// URI for that chunk (NULL if upload failed).
            transcript_segments JSONB NOT NULL DEFAULT '[]',
            transcript TEXT,
            summary TEXT,
            topics JSONB NOT NULL DEFAULT '[]',
            action_items JSONB NOT NULL DEFAULT '[]',
            attendee_names JSONB NOT NULL DEFAULT '[]',
            manager_notes TEXT,
            summary_model VARCHAR(80),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            signed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            signed_at TIMESTAMPTZ,
            signature_name VARCHAR(200),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_safety_meetings_company_started
        ON safety_meetings (company_id, started_at DESC)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS safety_meetings")
