"""add payer_medical_policies and payer_policy_embeddings tables

Revision ID: zm0n1o2p3q4r
Revises: zl9m0n1o2p3q
Create Date: 2026-03-22
"""
from alembic import op


revision = "zm0n1o2p3q4r"
down_revision = "zl9m0n1o2p3q"
branch_labels = None
depends_on = None


def upgrade():
    # Payer medical policies — coverage criteria keyed by (payer, procedure)
    op.execute("""
        CREATE TABLE IF NOT EXISTS payer_medical_policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            payer_name VARCHAR(100) NOT NULL,
            payer_type VARCHAR(50),
            policy_number VARCHAR(100),
            policy_title TEXT,
            procedure_codes TEXT[],
            diagnosis_codes TEXT[],
            procedure_description TEXT,
            coverage_status VARCHAR(30) NOT NULL DEFAULT 'conditional',
            requires_prior_auth BOOLEAN DEFAULT false,
            clinical_criteria TEXT,
            documentation_requirements TEXT,
            medical_necessity_criteria TEXT,
            age_restrictions VARCHAR(100),
            frequency_limits VARCHAR(200),
            place_of_service TEXT[],
            effective_date DATE,
            last_reviewed DATE,
            source_url TEXT,
            source_document TEXT,
            research_source VARCHAR(30) DEFAULT 'gemini',
            cms_document_id INTEGER,
            cms_document_type VARCHAR(10),
            cms_document_version INTEGER,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(payer_name, policy_number)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_payer_policies_payer_name
        ON payer_medical_policies(payer_name)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_payer_policies_procedure_codes
        ON payer_medical_policies USING GIN(procedure_codes)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_payer_policies_coverage
        ON payer_medical_policies(payer_name, coverage_status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_payer_policies_cms_doc
        ON payer_medical_policies(cms_document_id)
    """)

    # Payer policy embeddings — one embedding per policy for RAG search
    op.execute("""
        CREATE TABLE IF NOT EXISTS payer_policy_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            policy_id UUID NOT NULL REFERENCES payer_medical_policies(id) ON DELETE CASCADE,
            payer_name VARCHAR(100) NOT NULL,
            content TEXT NOT NULL,
            embedding vector(768) NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(policy_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_payer_policy_embeddings_payer
        ON payer_policy_embeddings(payer_name)
    """)

    # Payer mode on mw_threads
    op.execute("""
        ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS payer_mode BOOLEAN NOT NULL DEFAULT false
    """)


def downgrade():
    op.execute("ALTER TABLE mw_threads DROP COLUMN IF EXISTS payer_mode")
    op.execute("DROP INDEX IF EXISTS idx_payer_policy_embeddings_payer")
    op.execute("DROP TABLE IF EXISTS payer_policy_embeddings")
    op.execute("DROP INDEX IF EXISTS idx_payer_policies_cms_doc")
    op.execute("DROP INDEX IF EXISTS idx_payer_policies_coverage")
    op.execute("DROP INDEX IF EXISTS idx_payer_policies_procedure_codes")
    op.execute("DROP INDEX IF EXISTS idx_payer_policies_payer_name")
    op.execute("DROP TABLE IF EXISTS payer_medical_policies")
