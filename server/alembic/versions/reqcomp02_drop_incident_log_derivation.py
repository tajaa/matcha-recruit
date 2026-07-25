"""Drop the wvp_incident_log derivation_key — make the violent-incident-log
clause attest-only.

Revision ID: reqcomp02
Revises: reqcomp01
Create Date: 2026-07-24

`_derive_wvp_incident_log` used to return `compliant` for SB 553's
violent-incident-log obligation (Cal. Lab. Code § 6401.9(c)) on a single
free-text ILIKE match against `ir_incidents` ("%violen%"/"%threat%" in a
behavioral incident's title/description). A matching incident title proves an
incident was mentioned, not that the statute's log — with its required fields
and 5-year retention — exists. That is exactly the overclaim
`compliance_status.py`'s blind-never-violating invariant exists to block, so
the derivation is removed in the same PR that ships this migration
(`COMPONENT_DERIVATIONS` no longer has a `wvp_incident_log` entry).

`scripts/seed/sb553_components.sql` is `ON CONFLICT DO NOTHING` and was
edited to stop writing `derivation_key = 'wvp_incident_log'` going forward —
but that edit alone cannot repair a `violent_incident_log` row already
inserted by an earlier run of the pack in dev or prod. This is the one-time,
set-based data fix for those existing rows: the clause becomes attestable
(like `written_plan`/`hazard_assessment`) rather than permanently `unknown`
with no derivation and no attest path.

No DDL — a single UPDATE, safe to rehearse and to run against prod like any
other data-fix migration in this repo.
"""

from alembic import op


revision = "reqcomp02"
down_revision = "reqcomp01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE requirement_components
        SET derivation_key = NULL, updated_at = NOW()
        WHERE derivation_key = 'wvp_incident_log'
        """
    )


def downgrade():
    # Reverts a correctness fix, not something to run — restores the old
    # (wrong) derivation_key so the pre-migration behavior comes back if this
    # revision is ever rolled back. Scoped to the known component_key rather
    # than "any row with a NULL derivation_key" so it can't touch the other
    # attest-only clauses (written_plan/hazard_assessment/annual_review),
    # which never had a derivation_key to begin with.
    op.execute(
        """
        UPDATE requirement_components
        SET derivation_key = 'wvp_incident_log', updated_at = NOW()
        WHERE component_key = 'violent_incident_log' AND derivation_key IS NULL
        """
    )
