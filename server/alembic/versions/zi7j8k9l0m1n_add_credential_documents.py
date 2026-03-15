"""add credential_documents table for healthcare doc uploads

Revision ID: zi7j8k9l0m1n
Revises: zh6i7j8k9l0m
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "zi7j8k9l0m1n"
down_revision = "zh6i7j8k9l0m"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS credential_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            document_type VARCHAR(50) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            mime_type VARCHAR(100),
            file_size INTEGER,
            extracted_data JSONB,
            extraction_status VARCHAR(20) DEFAULT 'pending',
            review_status VARCHAR(20) DEFAULT 'pending',
            reviewed_by UUID REFERENCES users(id),
            reviewed_at TIMESTAMP,
            review_notes TEXT,
            uploaded_by UUID REFERENCES users(id),
            uploaded_via VARCHAR(20) DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cred_docs_employee ON credential_documents(employee_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cred_docs_company ON credential_documents(company_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS credential_documents")
