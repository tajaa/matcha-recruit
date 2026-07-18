"""One FNOL per incident — partial unique index on insurance_claims.

Revision ID: brokerquote03
Revises: brokerquote02
Create Date: 2026-07-18

`POST /broker/clients/{id}/insurance/fnol` had no dedupe: posting the same
`incident_id` twice inserted two claim rows sharing one deterministic
`claim_ref` (the ref is derived from the incident number). Against a live
carrier that is a duplicate claim filed on a single injury.

The route now guards with `ON CONFLICT (incident_id) WHERE kind = 'fnol'`,
which needs this partial unique index to infer — and the index is what makes
the guard hold under concurrent posts rather than just sequential ones.

Scoped to `kind = 'fnol'` on purpose: loss-run imports carry a NULL
`incident_id` and must stay unconstrained.

Dedupes pre-existing duplicates first (set-based, keeping the earliest row per
incident) so index creation cannot fail on live rows.

NOT fully reversible: `downgrade()` drops the index, but the duplicate FNOL rows
`upgrade()` deletes are gone — the RDS snapshot is the only rollback for those.
In practice there is nothing to delete on prod (`insurance_claims` ships in
brokerquote02, in this same unreleased bundle); the dedupe pass exists for dev
DBs that already took FNOLs through the unguarded route.
"""

from alembic import op


revision = "brokerquote03"
down_revision = "brokerquote02"
branch_labels = None
depends_on = None


def upgrade():
    # Keep the earliest FNOL per incident; drop later duplicates. ctid breaks
    # ties so the pass is deterministic even if created_at collides.
    op.execute(
        """
        DELETE FROM insurance_claims a
        USING (
            SELECT ctid,
                   ROW_NUMBER() OVER (
                       PARTITION BY incident_id
                       ORDER BY created_at ASC, ctid ASC
                   ) AS rn
            FROM insurance_claims
            WHERE kind = 'fnol' AND incident_id IS NOT NULL
        ) dup
        WHERE a.ctid = dup.ctid AND dup.rn > 1
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_insurance_claims_fnol_incident "
        "ON insurance_claims(incident_id) WHERE kind = 'fnol'"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_insurance_claims_fnol_incident")
