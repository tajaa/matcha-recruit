"""Per-requirement compliance status — is this tenant actually IN or OUT?

Revision ID: reqstatus01
Revises: crhist01
Create Date: 2026-07-17

The catalog says what the law requires. Nothing said whether the business obeys
it. The only in/out signal in the product was minimum wage — `_violation_count_
for_row` (compliance_service.py) returns None for every other category — so the
risk cockpit's "Est. penalty exposure" was, in truth, a minimum-wage number, and
`risk_index._compliance_component` scored "share of locations with >=1 non-expired
requirement row", i.e. whether WE researched their law. A company violating all
500 of its obligations scored 100/100.

Without a per-requirement status there is no such thing as risk of
non-compliance: a penalty range is a statutory CEILING ("what it would cost IF
you were violating this"), not an exposure. This table is that missing fact.

Two decisions worth keeping:

  * **Keyed on the CATALOG row, not the projection.** `compliance_requirements`
    rows are re-projected on every check and churn (a live run watched a
    location go 22 -> 17 codified rows between two checks as the research path
    rewrote them); `jurisdiction_requirements.id` is the stable identity. A
    projection row with no `jurisdiction_requirement_id` (~20% — written by live
    research that bypassed the catalog) therefore cannot carry status, which is
    honest: those rows fail the codified gate and no tenant can see them anyway.

  * **`unknown` is the default and means unknown.** Not compliant. The evals'
    rule — unmeasured is null, never 100 — applies with money attached: scoring
    a blind spot as clean is how a broker hands an underwriter a number that
    understates the book.

`basis` records HOW we know ('derived' = the system compared facts it holds,
'attested' = a human said so), mirroring `epl_readiness.ATTESTED_KEYS`, so a
roll-up can report derived and attested coverage separately instead of laundering
one into the other.

`requirement_status_audit_log` deliberately carries **no FK to the status row**:
per crhist01, history must survive the pruning of the thing it describes.
"""

from alembic import op


revision = "reqstatus01"
down_revision = "crhist01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS requirement_compliance_status (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id    UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            jurisdiction_requirement_id UUID NOT NULL
                             REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
            regulation_key TEXT,
            status         VARCHAR(14) NOT NULL DEFAULT 'unknown'
                             CHECK (status IN ('compliant','non_compliant','in_progress','unknown')),
            basis          VARCHAR(10)
                             CHECK (basis IN ('derived','attested')),
            evidence       JSONB,
            attested_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            attested_at    TIMESTAMPTZ,
            attested_note  TEXT,
            derived_at     TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (location_id, jurisdiction_requirement_id)
        )
        """
    )
    # The read is always "this company's open exposure" — status-first ordering.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_req_status_company_status "
        "ON requirement_compliance_status (company_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_req_status_location "
        "ON requirement_compliance_status (location_id)"
    )
    # Partial: the exposure roll-up only ever scans non_compliant rows.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_req_status_open "
        "ON requirement_compliance_status (company_id, jurisdiction_requirement_id) "
        "WHERE status = 'non_compliant'"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS requirement_status_audit_log (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id    UUID,
            jurisdiction_requirement_id UUID,
            action         VARCHAR(24) NOT NULL,
            from_status    VARCHAR(14),
            to_status      VARCHAR(14),
            basis          VARCHAR(10),
            actor_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            details        JSONB,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_req_status_audit_company "
        "ON requirement_status_audit_log (company_id, created_at DESC)"
    )

    # A requirement the tenant is confirmed to be violating is an issue like any
    # other, so it rides the remediation trail that already exists (dismiss /
    # note / reopen / auto-resolve + audit) rather than growing a parallel one.
    # compliedrem01 froze the vocabulary to the four live-computed sources.
    op.execute("ALTER TABLE compliance_issue_state DROP CONSTRAINT IF EXISTS compliance_issue_state_source_check")
    op.execute(
        "ALTER TABLE compliance_issue_state ADD CONSTRAINT compliance_issue_state_source_check "
        "CHECK (source IN ('wage','credential','incident','alert','requirement'))"
    )


def downgrade():
    op.execute("ALTER TABLE compliance_issue_state DROP CONSTRAINT IF EXISTS compliance_issue_state_source_check")
    # Any 'requirement' rows must go before the narrower CHECK can be restored.
    op.execute("DELETE FROM compliance_issue_state WHERE source = 'requirement'")
    op.execute(
        "ALTER TABLE compliance_issue_state ADD CONSTRAINT compliance_issue_state_source_check "
        "CHECK (source IN ('wage','credential','incident','alert'))"
    )
    op.execute("DROP TABLE IF EXISTS requirement_status_audit_log")
    op.execute("DROP TABLE IF EXISTS requirement_compliance_status")
