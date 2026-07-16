"""Un-quote jurisdiction_requirements.change_status — the drift flag nothing could read

Every stored value carries literal single quotes: the column holds `'new'`
(5 chars) and `'unchanged'` (11), not `new` and `unchanged`. Every reader
compares against the bare word, so the comparisons are structurally dead:

    changed_count | new_count | needs_review | new_if_unquoted | unchanged_if_unquoted
                0 |         0 |            0 |            1348 |                   433

That is `admin.py:5139-5140` reporting 0/0 where the truth is 1348/433, the
`needs_review` filter (`admin.py:4283`, `:4305`) never matching a row, and the
partial index `idx_jr_needs_review` sitting permanently empty. It also silently
disarms the codification pipeline's last stage: `propagate_drift_to_requirements`
writes `change_status='needs_review'` to raise drift, into a column whose readers
cannot match it.

The writer is the column DEFAULT, not application code. `'''new'''` is the SQL
literal for the 5-char string `'new'` — the classic `server_default="'new'"`
double-quoting. Nothing in the repo reproduces it: migration `t5u6v7w8x9y0:23`,
`database.py:3180`, and `orm/requirement.py:160` all correctly say `DEFAULT 'new'`,
and every SQL literal that writes the column (`compliance_service.py:2282`) is
bare. The INSERT path never names the column, so the DEFAULT supplies it — which
is why 232 rows created in the last 7 days are still quoted. Whatever ALTERed it
predates the current tree; both dev and prod carry it identically (prod: 1156
`'new'` + 436 `'unchanged'` of 1592 rows), consistent with dev having been cloned
from prod. It is the only quoted default in the schema.

So: fix the default (stops new rows), then backfill (fixes the 1781). No code
change is needed for the fix to hold.

Revision ID: chgstatus01
Revises: irdocvia01
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op


revision: str = "chgstatus01"
down_revision: Union[str, Sequence[str], None] = "irdocvia01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The documented vocabulary (t5u6v7w8x9y0's docstring): new | changed |
# unchanged | needs_review. btrim only strips the quote character, so a value
# outside this set is un-quoted and left alone rather than dropped — an unknown
# status is somebody else's bug, not this migration's to silently eat.
_QUOTE = "''''"  # a single ' , escaped for SQL


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Stop the bleeding: the DEFAULT is what quotes every new row.
    conn.exec_driver_sql(
        "ALTER TABLE jurisdiction_requirements "
        "ALTER COLUMN change_status SET DEFAULT 'new'"
    )

    # 2. Backfill. Set-based, one statement. Guarded on the quote so a re-run is
    #    a no-op and an already-clean row is untouched.
    conn.exec_driver_sql(
        f"""
        UPDATE jurisdiction_requirements
        SET change_status = btrim(change_status, {_QUOTE})
        WHERE change_status IS NOT NULL
          AND change_status LIKE {_QUOTE} || '%' || {_QUOTE}
        """
    )

    # 3. Post-check: no quoted value may survive. Raising here rolls the whole
    #    upgrade back (and is what MIGRATE_REHEARSAL=1 exercises).
    left = conn.exec_driver_sql(
        f"SELECT count(*) FROM jurisdiction_requirements "
        f"WHERE change_status LIKE {_QUOTE} || '%'"
    ).scalar()
    if left:
        raise RuntimeError(f"chgstatus01: {left} quoted change_status rows survived the backfill")


def downgrade() -> None:
    """Restores the prior state, quotes and all — i.e. deliberately re-breaks the
    readers. Exact: before the upgrade every row was quoted (dev 1348+433=1781 of
    1781; prod 1156+436=1592 of 1592), so re-quoting every non-null row reproduces
    it. Rows written as bare `needs_review` after the upgrade get quoted too,
    which matches what the pre-fix system would have stored anyway.
    """
    conn = op.get_bind()
    conn.exec_driver_sql(
        "ALTER TABLE jurisdiction_requirements "
        "ALTER COLUMN change_status SET DEFAULT '''new'''"
    )
    conn.exec_driver_sql(
        f"""
        UPDATE jurisdiction_requirements
        SET change_status = {_QUOTE} || change_status || {_QUOTE}
        WHERE change_status IS NOT NULL
          AND change_status NOT LIKE {_QUOTE} || '%'
        """
    )
