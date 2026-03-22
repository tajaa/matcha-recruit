"""add compliance_embeddings table, impact_summary on alerts, conversation_type on ai_conversations, policy_change_log

Revision ID: zl9m0n1o2p3q
Revises: zk8l9m0n1o2p
Create Date: 2026-03-22
"""
from alembic import op


revision = "zl9m0n1o2p3q"
down_revision = "zk8l9m0n1o2p"
branch_labels = None
depends_on = None


def upgrade():
    # Compliance embeddings — one embedding per jurisdiction_requirements row for RAG Q&A
    op.execute("""
        CREATE TABLE IF NOT EXISTS compliance_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            requirement_id UUID NOT NULL REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            embedding vector(768) NOT NULL,
            category VARCHAR(50),
            jurisdiction_level VARCHAR(20),
            jurisdiction_name VARCHAR(100),
            applicable_industries TEXT[],
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(requirement_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_compliance_embeddings_jurisdiction
        ON compliance_embeddings(jurisdiction_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_compliance_embeddings_category
        ON compliance_embeddings(category)
    """)

    # Impact summary on compliance alerts
    op.execute("""
        ALTER TABLE compliance_alerts
        ADD COLUMN IF NOT EXISTS impact_summary TEXT
    """)

    # Conversation type on ai_conversations
    op.execute("""
        ALTER TABLE ai_conversations
        ADD COLUMN IF NOT EXISTS conversation_type VARCHAR(30) DEFAULT 'general'
    """)

    # Policy change log — granular per-field change tracking
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_change_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            requirement_id UUID NOT NULL REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            field_changed VARCHAR(100) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_at TIMESTAMP DEFAULT NOW(),
            change_source VARCHAR(50),
            change_reason TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_policy_change_log_requirement
        ON policy_change_log(requirement_id, changed_at)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_policy_change_log_requirement")
    op.execute("DROP TABLE IF EXISTS policy_change_log")
    op.execute("ALTER TABLE ai_conversations DROP COLUMN IF EXISTS conversation_type")
    op.execute("ALTER TABLE compliance_alerts DROP COLUMN IF EXISTS impact_summary")
    op.execute("DROP INDEX IF EXISTS idx_compliance_embeddings_category")
    op.execute("DROP INDEX IF EXISTS idx_compliance_embeddings_jurisdiction")
    op.execute("DROP TABLE IF EXISTS compliance_embeddings")
