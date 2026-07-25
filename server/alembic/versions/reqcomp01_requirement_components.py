"""Per-requirement component decomposition — one statute, several checkable clauses.

Revision ID: reqcomp01
Revises: penaltyauth01
Create Date: 2026-07-24

`requirement_compliance_status` (reqstatus01) answers "is this tenant in or out"
at the granularity of one whole catalog row. Some statutes are not one fact —
CA SB 553 (Cal. Lab. Code § 6401.9, catalog row `workplace_violence_prevention`
for the CA jurisdiction) reads as five distinct obligations: a written plan,
annual training, a violent-incident log, a hazard assessment, an annual review.
Collapsing them into one status either hides four gaps behind one green check or
manufactures one red gap the tenant cannot act on ("fix what, exactly?").

`requirement_components` is the decomposition, keyed on the CATALOG row like the
rest of this system — so it is shared SSOT, not per-tenant: decomposing one
state's statute once serves every tenant scoped to that jurisdiction, same
economics as the `vertical_coverage` ledger. `component_key` is per-parent
(`UNIQUE (jurisdiction_requirement_id, component_key)`), not global — the same
`regulation_key` (`workplace_violence_prevention`) already spans unrelated
statutes across states (compare the CA plan-based law to Texas SB 240's
healthcare-only regime), so component sets never share a name across parents.

Widening `requirement_compliance_status`/`requirement_status_audit_log` with a
nullable `component_key` is additive: existing whole-requirement rows keep
`component_key IS NULL` and no backfill runs. Postgres treats NULLs as distinct
in a plain unique index, so the replacement uniqueness constraint is expressed
as `(location_id, jurisdiction_requirement_id, COALESCE(component_key, ''))` —
without the COALESCE, the pre-existing whole-requirement row could be inserted
repeatedly and the `ON CONFLICT` upserts in `compliance_status.py` would start
raising "no unique or exclusion constraint matching the ON CONFLICT specification".

No change needed to `compliance_issue_state.source` — reqstatus01 already added
'requirement' to that CHECK.
"""

from alembic import op


revision = "reqcomp01"
down_revision = "penaltyauth01"
branch_labels = None
depends_on = None

# The real, environment-specific name of the constraint reqstatus01 created via
# a bare `UNIQUE (location_id, jurisdiction_requirement_id)` column constraint
# (Postgres auto-names these; verified against the running dev DB rather than
# guessed, since a name off by one character makes DROP CONSTRAINT IF EXISTS a
# silent no-op and the old constraint would keep colliding with component rows).
_OLD_UNIQUE = "requirement_compliance_status_location_id_jurisdiction_requ_key"


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS requirement_components (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            jurisdiction_requirement_id UUID NOT NULL
                             REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            component_key  VARCHAR(48) NOT NULL,
            label          TEXT NOT NULL,
            question       TEXT NOT NULL,
            statute_citation TEXT,
            suggested_fix  TEXT,
            severity       VARCHAR(12) NOT NULL DEFAULT 'important'
                             CHECK (severity IN ('critical','important','recommended')),
            derivation_key VARCHAR(48),
            sort_order     INTEGER NOT NULL DEFAULT 0,
            verified_at    TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (jurisdiction_requirement_id, component_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_req_components_parent "
        "ON requirement_components (jurisdiction_requirement_id, sort_order)"
    )

    op.execute(
        "ALTER TABLE requirement_compliance_status "
        "ADD COLUMN IF NOT EXISTS component_key VARCHAR(48)"
    )
    op.execute(
        "ALTER TABLE requirement_status_audit_log "
        "ADD COLUMN IF NOT EXISTS component_key VARCHAR(48)"
    )

    op.execute(
        f'ALTER TABLE requirement_compliance_status DROP CONSTRAINT IF EXISTS "{_OLD_UNIQUE}"'
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_req_status_loc_cat_component "
        "ON requirement_compliance_status "
        "(location_id, jurisdiction_requirement_id, COALESCE(component_key, ''))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ux_req_status_loc_cat_component")
    # Delete component rows before restoring the 2-column uniqueness — a
    # surviving component row on the same (location, catalog) pair as the
    # whole-requirement row would violate the restored constraint.
    op.execute(
        "DELETE FROM requirement_compliance_status WHERE component_key IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE requirement_compliance_status "
        "ADD CONSTRAINT requirement_compliance_status_location_id_jurisdiction_requ_key "
        "UNIQUE (location_id, jurisdiction_requirement_id)"
    )
    op.execute(
        "ALTER TABLE requirement_status_audit_log DROP COLUMN IF EXISTS component_key"
    )
    op.execute(
        "ALTER TABLE requirement_compliance_status DROP COLUMN IF EXISTS component_key"
    )
    op.execute("DROP TABLE IF EXISTS requirement_components")
