"""compliance_requirement_history must survive the prune it exists to record

The projection prune snapshots a requirement, then deletes it
(`compliance_service.py:3741-3744`):

    await _snapshot_to_history(conn, stale, location_id)
    await conn.execute("DELETE FROM compliance_requirements WHERE id = $1", stale_id)

…but the history row points at that requirement through a CASCADE:

    compliance_requirement_history_requirement_id_fkey
      FOREIGN KEY (requirement_id) REFERENCES compliance_requirements(id) ON DELETE CASCADE

so the DELETE on the next line erases the row just written — and every earlier
history row for the same requirement with it. The prune path preserves exactly
nothing, while reading as though it preserves everything. Same shape at the
duplicate-cleanup path (`:3518-3522`). Live state agrees: 675 history rows and
**0** whose requirement is gone.

The catalog's audit table got this right on purpose, and is the precedent here —
`jrver01:55`: *"No FK: versions must survive the requirement's (and
jurisdiction's) delete."* So: drop the FK rather than soften it to SET NULL.
`requirement_id` is the join key every reader uses
(`idx_compliance_requirement_history_requirement`), and NULLing it would strand
the row just as dead, only quieter.

`location_id`'s CASCADE is deliberately left alone: history for a location that
no longer exists has nobody to answer to, and that FK is not on the prune path.

This does not recover what was already destroyed — those rows are gone. It stops
the loss.

Revision ID: crhist01
Revises: chgstatus01
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op


revision: str = "crhist01"
down_revision: Union[str, Sequence[str], None] = "chgstatus01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK = "compliance_requirement_history_requirement_id_fkey"


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        f"ALTER TABLE compliance_requirement_history DROP CONSTRAINT IF EXISTS {_FK}"
    )

    # Post-check: the constraint must be gone, or the prune keeps eating history
    # silently and this migration reported success for nothing.
    still_there = conn.exec_driver_sql(
        f"""
        SELECT count(*) FROM pg_constraint
        WHERE conrelid = 'compliance_requirement_history'::regclass
          AND contype = 'f' AND conname = '{_FK}'
        """
    ).scalar()
    if still_there:
        raise RuntimeError(f"crhist01: {_FK} survived the drop")


def downgrade() -> None:
    """Re-adds the CASCADE, i.e. restores the data-eating behaviour.

    NOT VALID because history rows written while the fix was in place legitimately
    reference requirements that have since been pruned — the exact rows this
    migration exists to keep. Validating would fail on them, and deleting them to
    make the downgrade pass would re-inflict the bug by hand.
    """
    conn = op.get_bind()
    conn.exec_driver_sql(
        f"""
        ALTER TABLE compliance_requirement_history
        ADD CONSTRAINT {_FK}
        FOREIGN KEY (requirement_id) REFERENCES compliance_requirements(id)
        ON DELETE CASCADE
        NOT VALID
        """
    )
