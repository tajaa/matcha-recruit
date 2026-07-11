"""Grounding tier-2b verdict cache — compliance_eval_grounding_verdicts.

The adversarial LLM verifier (grounding_verifier.py) makes one Gemini call per
grounded row tier-1 can't settle. "Run only on new/changed rows" needs a durable
marker, and the eval system is read-only over the catalog — so the verdict cannot
live on jurisdiction_requirements. This eval-owned table caches each verdict keyed
on (requirement_id, input_hash) where input_hash = sha256(current_value + cited
excerpts): change the value or the corpus and the hash changes → re-verify;
otherwise the cached verdict is reused for 0 Gemini calls.

Revision ID: groundver01
Revises: oshakeys01
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "groundver01"
down_revision: Union[str, Sequence[str], None] = "oshakeys01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS compliance_eval_grounding_verdicts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            requirement_id UUID NOT NULL
                REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            input_hash VARCHAR(64) NOT NULL,
            verdict VARCHAR(20) NOT NULL
                CHECK (verdict IN ('llm_confirmed', 'llm_refuted', 'llm_unclear')),
            model VARCHAR(80) NOT NULL,
            reasoning TEXT,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (requirement_id, input_hash)
        )
    """))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_grounding_verdicts_requirement "
        "ON compliance_eval_grounding_verdicts (requirement_id)"
    ))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS compliance_eval_grounding_verdicts"))
