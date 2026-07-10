"""scope_codifications — the stored link between a scope classification and the
jurisdiction_requirements row that codifies it.

Today "codified" is inferred fresh on every read by string-matching
regulation_key. This records it as a fact with provenance (which run codified
it, when), so the scope→store seam is auditable rather than a hopeful join. The
read paths (resolve_scope/labor_scope) still use the fast string join; this
table is written by the reconcile sweep + the fetch-queue research endpoint.

Revision ID: codify02
Revises: codify01
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op


revision: str = "codify02"
down_revision: Union[str, Sequence[str], None] = "codify01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS scope_codifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            classification_id UUID NOT NULL
                REFERENCES authority_item_classifications(id) ON DELETE CASCADE,
            jurisdiction_requirement_id UUID NOT NULL
                REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            regulation_key TEXT NOT NULL,
            jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE CASCADE,
            source VARCHAR(20) NOT NULL DEFAULT 'reconcile',
            run_info JSONB,
            codified_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (classification_id, jurisdiction_requirement_id)
        )
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_scope_codifications_requirement "
        "ON scope_codifications(jurisdiction_requirement_id)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_scope_codifications_classification "
        "ON scope_codifications(classification_id)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DROP TABLE IF EXISTS scope_codifications")
