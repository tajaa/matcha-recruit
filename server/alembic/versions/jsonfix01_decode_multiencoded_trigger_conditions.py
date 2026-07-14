"""Un-mangle trigger_conditions / applicable_entity_types that were re-encoded.

asyncpg hands JSONB back as a `str`. Every research pass reads a requirement out
of the catalog, turns it into a dict, and writes it back — and the upsert did
`json.dumps(value)` unconditionally. So each pass wrapped the value in one more
layer of escaping:

    {"type": "entity_type", "value": "behavioral_health"}
    "{\\"type\\": \\"entity_type\\", \\"value\\": \\"behavioral_health\\"}"
    "\\"{\\\\\\"type\\\\\\": \\\\\\"entity_type\\\\\\", ...}\\""

Once it is a JSON *string* rather than an object, the trigger evaluator can't
read it and the requirement fails OPEN — it applies to everybody. That is how a
Los Angeles dental practice was served SAMHSA Opioid Treatment Program
certification (trigger: entity_type == behavioral_health) and Hospital Inpatient
Quality Reporting (trigger: payer_contracts contains medicare).

The writer is fixed in compliance_service._as_jsonb. This unwraps what is already
stored: repeatedly json.loads until it stops being a string, then write the value
back as real JSONB. Rows that are already objects are untouched. Anything that
never parses is left exactly as-is and reported — a value we can't read is not a
value we should guess at.

Idempotent: re-running finds nothing to unwrap.

Revision ID: jsonfix01
Revises: jparent01
Create Date: 2026-07-14
"""
import json

from alembic import op
from sqlalchemy import text

revision = "jsonfix01"
down_revision = "jparent01"
branch_labels = None
depends_on = None

_COLS = ("trigger_conditions", "applicable_entity_types")


def _unwrap(raw):
    """Peel encoding layers until it stops being a JSON string. None if unreadable."""
    value = raw
    for _ in range(6):
        if not isinstance(value, str):
            return value
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return None


def upgrade() -> None:
    conn = op.get_bind()

    fixed = unreadable = 0
    for col in _COLS:
        rows = conn.execute(
            text(f"SELECT id, {col}::text AS raw FROM jurisdiction_requirements "
                 f"WHERE {col} IS NOT NULL")
        ).mappings().all()

        for r in rows:
            # ::text always gives us JSON text; one loads() gets the stored value.
            try:
                stored = json.loads(r["raw"])
            except (TypeError, ValueError):
                unreadable += 1
                continue

            if not isinstance(stored, str):
                continue  # already a proper object/array — nothing to do

            value = _unwrap(stored)
            if value is None or isinstance(value, str):
                # Either unreadable, or it decodes to a bare string that was never
                # an object. Leave it; don't invent structure.
                unreadable += 1
                continue

            conn.execute(
                # CAST(...), not `:v::jsonb` — asyncpg reads `::` after a param
                # marker as part of the placeholder and raises a syntax error.
                text(f"UPDATE jurisdiction_requirements SET {col} = CAST(:v AS jsonb) WHERE id = :id"),
                {"v": json.dumps(value), "id": r["id"]},
            )
            fixed += 1

    print(f"[jsonfix01] decoded={fixed} unreadable_left_alone={unreadable}")


def downgrade() -> None:
    # Re-encoding correct JSON back into escaped strings would restore the bug.
    pass
