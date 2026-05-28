"""Backfill orphaned company_compliance_scope rows into the live compliance_requirements store.

The gap-analysis wizard used to write its resolved "covered" scope into
company_compliance_scope — a pointer table nothing reads. Now that finalize projects
into compliance_requirements (the live single source of truth), this one-time backfill
materializes any scope rows written by the OLD code path so historical wizard output
becomes visible on /app/compliance and /admin/compliance-mgmt.

Projection mirrors the cherry-pick projector exactly: the same requirement_key formula
(category:regulation_key|title) and the catalog FK (jurisdiction_requirement_id) for
dedup. governance_source carries the original scope.source ('onboarding_wizard' /
'employee_sync').

Dedup: ON CONFLICT on the (location_id, jurisdiction_requirement_id) partial unique
index skips rows already projected/scanned WITH a populated FK. NOTE: a legacy scan row
with the SAME content but a NULL FK (pre-FK migration) won't collide and can leave a
transient duplicate — this self-heals on the next scan (which fills the FK) and is the
known string-vs-FK key tradeoff; quantify pre/post counts on dev before prod.

Idempotent. downgrade is a no-op (backfilled rows are indistinguishable from
legitimately-projected ones once live; deleting by provenance would also remove rows
finalize wrote post-migration).

Revision ID: cmpreqbf02
Revises: cmpreqfk01
Create Date: 2026-05-28
"""
from alembic import op


revision = "cmpreqbf02"
down_revision = "cmpreqfk01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The catalog widened jurisdiction_requirements.current_value to VARCHAR(500)
    # (international requirements — migration s4t5u6v7w8x9), but the live store's
    # compliance_requirements.current_value stayed VARCHAR(100). Match it before
    # copying, or long values truncate-error. This also fixes the same latent
    # truncation in the scan path (_upsert_requirement copies jr.current_value).
    op.execute(
        "ALTER TABLE compliance_requirements ALTER COLUMN current_value TYPE VARCHAR(500)"
    )
    op.execute(
        """
        INSERT INTO compliance_requirements (
            location_id, category, jurisdiction_level, jurisdiction_name,
            title, description, current_value, numeric_value,
            source_url, source_name, effective_date,
            requirement_key, governance_source, jurisdiction_requirement_id
        )
        SELECT
            s.location_id, jr.category, jr.jurisdiction_level, jr.jurisdiction_name,
            jr.title, jr.description, jr.current_value, jr.numeric_value,
            jr.source_url, jr.source_name, jr.effective_date,
            jr.category || ':' || COALESCE(jr.regulation_key, jr.title),
            LEFT(s.source, 20), jr.id
        FROM company_compliance_scope s
        JOIN jurisdiction_requirements jr ON jr.id = s.requirement_id
        WHERE s.status = 'active'
        ON CONFLICT (location_id, jurisdiction_requirement_id)
            WHERE jurisdiction_requirement_id IS NOT NULL DO NOTHING
        """
    )


def downgrade() -> None:
    # No-op: backfilled rows are indistinguishable from post-migration projections.
    pass
