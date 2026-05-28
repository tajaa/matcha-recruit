"""Link compliance_requirements back to the global jurisdiction_requirements catalog.

Part of the compliance SSOT consolidation. `compliance_requirements` is the live
per-company store every surface reads (customer /app/compliance, /admin/compliance-mgmt,
dashboard, brokers). Historically it was a pure denormalized snapshot with NO link to
the catalog row it was copied from — so the gap-analysis wizard wrote its resolved scope
into a separate, orphaned `company_compliance_scope` pointer table that nothing reads.

This adds `jurisdiction_requirement_id` (nullable FK → jurisdiction_requirements) so every
catalog-derived per-company row carries a real pointer to its content source. That FK
becomes the dedup identity: wizard finalize, the per-location scan, and the admin
cherry-pick all converge on `compliance_requirements` and de-duplicate on
(location_id, jurisdiction_requirement_id) instead of the fragile requirement_key string.

Hand-authored rows (admin overrides, Gemini-fresh rows with no catalog origin) leave the
FK null and continue to dedup on requirement_key.

ON DELETE SET NULL: a per-company snapshot is the live record and must survive catalog
churn; the FK is provenance/re-sync metadata, not an ownership edge.

Idempotent (IF NOT EXISTS) so re-running against a partially-upgraded DB is safe.

Revision ID: cmpreqfk01
Revises: mwseccmt01
Create Date: 2026-05-28
"""
from alembic import op


revision = "cmpreqfk01"
down_revision = "mwseccmt01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE compliance_requirements
        ADD COLUMN IF NOT EXISTS jurisdiction_requirement_id UUID
            REFERENCES jurisdiction_requirements(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_compliance_requirements_jr_id
            ON compliance_requirements(jurisdiction_requirement_id)
        """
    )
    # FK-identity dedup for catalog-derived rows. Partial so hand-authored rows
    # (null FK) are exempt and keep their (location_id, requirement_key) identity.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_compliance_requirements_loc_jr
            ON compliance_requirements(location_id, jurisdiction_requirement_id)
            WHERE jurisdiction_requirement_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_compliance_requirements_loc_jr")
    op.execute("DROP INDEX IF EXISTS idx_compliance_requirements_jr_id")
    op.execute(
        "ALTER TABLE compliance_requirements DROP COLUMN IF EXISTS jurisdiction_requirement_id"
    )
