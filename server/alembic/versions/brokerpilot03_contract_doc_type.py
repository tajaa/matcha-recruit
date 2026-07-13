"""Broker Pilot — allow doc_type 'contract' on uploaded documents

Revision ID: brokerpilot03
Revises: usageevents01
Create Date: 2026-07-13

The Contract-review mode asks the broker to upload the client's contract, so the
classifier now has a `contract` doc_type to land on (previously such a document
was forced into `other`/`policy_form`, and the mode's document requirement could
never be recognized as satisfied).

`broker_pilot_documents.doc_type` carries an inline CHECK from `brokerpilot01`,
so Postgres auto-named it `broker_pilot_documents_doc_type_check`. Drop-and-recreate
is the only way to widen it. IF EXISTS on the drop keeps this idempotent against a
DB where the constraint was already renamed or removed by hand.

Chained on `usageevents01` — the head of this branch
(brokerpilot01 → brokerpilot02 → discipcomp01 → usageevents01). The repo has
other unrelated heads; this migration deliberately does NOT merge them.
"""

from alembic import op


revision = "brokerpilot03"
down_revision = "usageevents01"
branch_labels = None
depends_on = None

_TYPES_NEW = ("loss_run", "dec_page", "quote", "carrier_letter", "bordereau",
              "policy_form", "financials", "contract", "other")
_TYPES_OLD = ("loss_run", "dec_page", "quote", "carrier_letter", "bordereau",
              "policy_form", "financials", "other")


def _check(values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{v}'" for v in values)
    return (
        "ALTER TABLE broker_pilot_documents "
        "ADD CONSTRAINT broker_pilot_documents_doc_type_check "
        f"CHECK (doc_type IN ({listed}))"
    )


def upgrade():
    op.execute(
        "ALTER TABLE broker_pilot_documents "
        "DROP CONSTRAINT IF EXISTS broker_pilot_documents_doc_type_check"
    )
    op.execute(_check(_TYPES_NEW))


def downgrade():
    # Contract-typed rows predate the narrower vocabulary — fold them back into
    # `other` (the classifier's own fallback) so the old CHECK can be restored.
    op.execute("UPDATE broker_pilot_documents SET doc_type = 'other' WHERE doc_type = 'contract'")
    op.execute(
        "ALTER TABLE broker_pilot_documents "
        "DROP CONSTRAINT IF EXISTS broker_pilot_documents_doc_type_check"
    )
    op.execute(_check(_TYPES_OLD))
