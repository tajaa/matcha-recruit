"""Drop the dead company_compliance_scope table.

Nothing in application code reads company_compliance_scope — grep confirms
zero SELECT/UPDATE/DELETE callsites (the only prior references were the
onboarding_scope_ai.py docstring, since fixed, and the migrations below).
cmpreqfk01 gave compliance_requirements a direct catalog FK
(jurisdiction_requirement_id) and finalize now projects into it via
_write_compliance_scope_rows; cmpreqbf02 already backfilled every historical
row this table held into compliance_requirements. The table has been a pure
write-sink with no reader since cmpreqbf02 landed.

NOT applied by this commit — author only, per the repo's production-safety
rule (DDL needs explicit approval). The migration tree currently has
multiple heads (see `alembic heads`); this chains off cmpreqbf02 and will
need a merge migration before `alembic upgrade head` can reach it.

Revision ID: cmpreqdrop01
Revises: cmpreqbf02
Create Date: 2026-07-13
"""
from alembic import op


revision = "cmpreqdrop01"
down_revision = "cmpreqbf02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_compliance_scope")


def downgrade() -> None:
    # Faithful reversal of the original DDL (zzzz_a01_admin_onboarding_scope.py) —
    # restores the table shape, not its data (see the module docstring).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_compliance_scope (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            requirement_id    UUID NOT NULL REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            location_id       UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            scope_level       TEXT NOT NULL,
            source            TEXT NOT NULL DEFAULT 'onboarding_wizard',
            status            TEXT NOT NULL DEFAULT 'active',
            admin_reviewed_by UUID REFERENCES users(id),
            added_at          TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (company_id, requirement_id, location_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_scope_company "
        "ON company_compliance_scope(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_scope_requirement "
        "ON company_compliance_scope(requirement_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_scope_location "
        "ON company_compliance_scope(location_id)"
    )
