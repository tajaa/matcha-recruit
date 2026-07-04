"""Legal Pilot robustness — matter jurisdiction + external legal research

Revision ID: legaldef02
Revises: mwtaskhtxt01
Create Date: 2026-07-04

Adds jurisdiction grounding to legal matters (`location_id` /
`jurisdiction_state`) and a `legal_matter_research` table that persists
CourtListener case-law search results + a grounded-Gemini guidance synthesis.
`cases` holds CourtListener API rows only — cids minted from these rows
(`case:<cluster_id>`) satisfy the `validate_citations` index-membership
invariant; `guidance` is informational synthesis, never citable.

NOTE: branchy alembic history — `down_revision` set to the current tip
(`mwtaskhtxt01`). Confirm the head for your environment before `alembic
upgrade`.
"""

from alembic import op


revision = "legaldef02"
down_revision = "mwtaskhtxt01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE legal_matters ADD COLUMN IF NOT EXISTS location_id UUID "
        "REFERENCES business_locations(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE legal_matters ADD COLUMN IF NOT EXISTS jurisdiction_state VARCHAR(2)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_matter_research (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            matter_id     UUID NOT NULL REFERENCES legal_matters(id) ON DELETE CASCADE,
            company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            status        VARCHAR(16) NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running','complete','failed')),
            query         TEXT,
            -- State the run was grounded in (resolved at run time). Read-time
            -- filters skip runs whose state no longer matches the matter's
            -- current jurisdiction, so a post-research location correction
            -- can't pair new-state governing law with old-state case law.
            jurisdiction_state VARCHAR(2),
            cases         JSONB,
            guidance      JSONB,
            error         TEXT,
            created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at  TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_legal_matter_research_matter "
        "ON legal_matter_research(matter_id, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS legal_matter_research")
    op.execute("ALTER TABLE legal_matters DROP COLUMN IF EXISTS jurisdiction_state")
    op.execute("ALTER TABLE legal_matters DROP COLUMN IF EXISTS location_id")
