"""Widen scope_codifications.source — VARCHAR(20) is a tripwire, not a constraint.

The column labels which pass wrote a codification link ('reconcile',
'backfill', 'research_run', 'manual', 'scheduled_research'). It buys no
integrity — it is a provenance breadcrumb, not an enum — but 20 chars is
narrow enough to bite:

  'scheduled_research'  = 18 chars  (the headless growth loop — 2 to spare)

A slightly more descriptive label overflows and asyncpg raises
StringDataRightTruncationError, which would abort the whole reconcile
transaction: links unwritten, citations unstamped. That is a silly way to
break the growth loop, and it already bit once during development.

VARCHAR(64) — wide enough that no reasonable label overflows, still narrow
enough to stay an obvious "short tag" rather than free text. Widening a
VARCHAR is a metadata-only catalog update in Postgres: no table rewrite, no
lock beyond a brief ACCESS EXCLUSIVE, safe on a live table.

NOT applied by this commit — author only, per the repo's production-safety
rule.

Revision ID: codify03
Revises: catseed01
Create Date: 2026-07-13
"""
from alembic import op


revision = "codify03"
down_revision = "catseed01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scope_codifications "
        "ALTER COLUMN source TYPE VARCHAR(64)"
    )


def downgrade() -> None:
    # Truncate anything that outgrew the old width first, or the narrowing
    # fails on exactly the rows this migration exists to permit.
    op.execute(
        "UPDATE scope_codifications SET source = LEFT(source, 20) "
        "WHERE LENGTH(source) > 20"
    )
    op.execute(
        "ALTER TABLE scope_codifications "
        "ALTER COLUMN source TYPE VARCHAR(20)"
    )
