"""Re-parent requirements to the jurisdiction whose level they claim.

THE BUG THIS FIXES
------------------
A requirement carries a *stamped* jurisdiction_level / jurisdiction_name, and
separately a jurisdiction_id FK to the node it hangs off. On ~63% of active rows
these disagree — rows stamped `state` hang off a CITY, rows stamped `national`
hang off a city, and so on.

Chain resolution (resolve_jurisdiction_stack) walks jurisdiction_id: city →
county → state → federal. So a row stamped "California / state" that physically
hangs off `Beverly Hills, CA` is **invisible to every other California city**.

That is not a cosmetic defect. Both "California State Minimum Wage" rows were
parented to city nodes, so a Los Angeles tenant's Compliance tab served *zero*
minimum-wage, overtime and meal-break requirements. The law was in the catalog
the whole time; the chain just couldn't reach it.

Root causes in the write path (fixed alongside this migration in
compliance_service._resolve_jurisdiction_id_for_level):
  1. no `national` case  -> fell through "unknown level, treat as city"
  2. every failed parent lookup silently fell back to the leaf
  3. 12 callsites bypassed routing entirely, writing to the leaf

WHAT IT DOES
------------
For every active row, resolve the jurisdiction it *should* hang off:
    federal/national -> that country's federal/national node
    state            -> the state node for the current parent's state
    county           -> the county node for (state, county)
    city             -> unchanged
Then either move it, or — when the correct parent ALREADY holds the same
requirement_key — MERGE, because those are the same obligation researched once
per city. They are duplicates, not data to lose.

A merge keeps the freshest row, repoints all 8 FK paths off the losers, and only
then deletes them. Three of those children carry uniques
(compliance_embeddings.requirement_id, uq_compliance_requirements_loc_jr,
scope_codifications(classification_id, jr_id)), so a repoint that would collide
drops the loser's child row instead of raising.

Rows we cannot place are LEFT ALONE and reported — never guessed at.

SET-BASED, ON PURPOSE
---------------------
The first cut of this migration was a row-by-row Python loop: a rival lookup per
row, then ~11 statements per merge. Locally that is merely slow; run against RDS
through an SSH tunnel it is ~20,000 sequential round-trips, and it simply does not
finish — the client sits in `idle in transaction / ClientRead` while every
statement pays the round-trip, and any timeout rolls the whole thing back.

So the same semantics are expressed as ~20 set-based statements against a TEMP
table. Same winners, same merges, same refusal to guess — just one round-trip per
*operation* instead of one per *row*.

CANONICAL_KEY
-------------
`canonical_key` is jurisdiction-ENCODED (`oh_cleveland_minor_work_permit_…`) and
UNIQUE, and is read by onboarding_scope_ai + the scope-registry shadow
reconciliation. A moved row's key names the jurisdiction it came FROM, which is
now a lie. The first cut never touched it and left rows on a STATE node whose key
says a CITY. Moved rows have it NULLed — it is nullable and recomputed on next
write; a stale identity is worse than an absent one.

Idempotent: re-running finds nothing to move.

Revision ID: jparent01
Revises: rekey02
Create Date: 2026-07-14
"""
import os

from alembic import op
from sqlalchemy import text

revision = "jparent01"
down_revision = "rekey02"
branch_labels = None
depends_on = None


# child table -> FK column. Repointed off merge losers before they are deleted.
# (jurisdiction_requirements.superseded_by_id is handled separately.)
_CHILD_FKS = [
    ("compliance_requirements", "jurisdiction_requirement_id"),
    ("scope_codifications", "jurisdiction_requirement_id"),
    ("compliance_embeddings", "requirement_id"),
    ("policy_change_log", "requirement_id"),
    ("repository_alerts", "requirement_id"),
    ("compliance_eval_findings", "requirement_id"),
    ("compliance_eval_grounding_verdicts", "requirement_id"),
]

# Children carrying a unique that a repoint can violate. Once N losers fold into
# one winner, every one of their child rows lands on the SAME key — so the
# survivors of that key must be collapsed to exactly one BEFORE the repoint.
#
# "Does the winner already have one?" is NOT enough, and the rehearsal proved it:
# when several losers merge into a winner that has NO embedding, none of them is
# deleted and they all repoint onto `unique (requirement_id)` ->
# UniqueViolationError. The row-by-row original never saw this because it merged
# one loser at a time — the first repoint made the winner "already have one", so
# the next was dropped. Set-based has to say what that loop MEANT: keep exactly
# one row per post-merge key, and always prefer the winner's own.
#
# `(m.winner IS NULL) DESC` sorts winner-owned rows first, so they always take
# rn = 1 and it is only ever a LOSER's row that gets deleted. Keyed on ctid so
# this needs no knowledge of each table's primary key.
_DEDUPE_BEFORE_REPOINT = [
    # compliance_embeddings: unique (requirement_id)
    """
    DELETE FROM compliance_embeddings t USING (
        SELECT e.ctid AS cid, ROW_NUMBER() OVER (
                   PARTITION BY COALESCE(m.winner, e.requirement_id)
                   ORDER BY (m.winner IS NULL) DESC, e.ctid
               ) AS rn
        FROM compliance_embeddings e
        LEFT JOIN _jp_merge m ON m.loser = e.requirement_id
        WHERE COALESCE(m.winner, e.requirement_id) IN (SELECT winner FROM _jp_merge)
    ) d
    WHERE t.ctid = d.cid AND d.rn > 1
    """,
    # compliance_requirements: unique (location_id, jurisdiction_requirement_id)
    # WHERE jurisdiction_requirement_id IS NOT NULL
    """
    DELETE FROM compliance_requirements t USING (
        SELECT c.ctid AS cid, ROW_NUMBER() OVER (
                   PARTITION BY c.location_id,
                                COALESCE(m.winner, c.jurisdiction_requirement_id)
                   ORDER BY (m.winner IS NULL) DESC, c.ctid
               ) AS rn
        FROM compliance_requirements c
        LEFT JOIN _jp_merge m ON m.loser = c.jurisdiction_requirement_id
        WHERE c.jurisdiction_requirement_id IS NOT NULL
          AND COALESCE(m.winner, c.jurisdiction_requirement_id)
              IN (SELECT winner FROM _jp_merge)
    ) d
    WHERE t.ctid = d.cid AND d.rn > 1
    """,
    # scope_codifications: unique (classification_id, jurisdiction_requirement_id)
    """
    DELETE FROM scope_codifications t USING (
        SELECT s.ctid AS cid, ROW_NUMBER() OVER (
                   PARTITION BY s.classification_id,
                                COALESCE(m.winner, s.jurisdiction_requirement_id)
                   ORDER BY (m.winner IS NULL) DESC, s.ctid
               ) AS rn
        FROM scope_codifications s
        LEFT JOIN _jp_merge m ON m.loser = s.jurisdiction_requirement_id
        WHERE COALESCE(m.winner, s.jurisdiction_requirement_id)
              IN (SELECT winner FROM _jp_merge)
    ) d
    WHERE t.ctid = d.cid AND d.rn > 1
    """,
]

# The target-parent resolver, as SQL. One definition, used by the plan, the move
# and the post-check, so all three agree on what "correct" means.
_TARGET_SQL = """
    CASE
      WHEN jr.jurisdiction_level IN ('federal','national') AND COALESCE(cj.country_code,'US') = 'US'
        THEN (SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US'
               ORDER BY created_at, id LIMIT 1)
      WHEN jr.jurisdiction_level IN ('federal','national')
        THEN (SELECT id FROM jurisdictions WHERE level = 'national' AND country_code = cj.country_code
               ORDER BY created_at, id LIMIT 1)
      WHEN jr.jurisdiction_level = 'state'
        THEN (SELECT id FROM jurisdictions WHERE level = 'state' AND state = cj.state
               ORDER BY created_at, id LIMIT 1)
      WHEN jr.jurisdiction_level = 'county'
        THEN (SELECT id FROM jurisdictions WHERE level = 'county'
                AND state = cj.state AND county = cj.county
               ORDER BY created_at, id LIMIT 1)
      ELSE jr.jurisdiction_id
    END
"""


def _ensure_missing_parents(conn) -> None:
    """Create parents the data needs but the tree lacks.

    Some national rows hang off a foreign city and some state rows off a city
    purely because no France / Georgia node exists. Both INSERTs are guarded, so
    they no-op where the node is already present.
    """
    conn.execute(text("""
        INSERT INTO jurisdictions (display_name, level, country_code, authority_type)
        SELECT 'France', 'national', 'FR', 'geographic'
        WHERE NOT EXISTS (
            SELECT 1 FROM jurisdictions WHERE level = 'national' AND country_code = 'FR'
        )
    """))
    fed_id = conn.execute(
        text("SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' "
             "ORDER BY created_at, id LIMIT 1")
    ).scalar()
    conn.execute(
        text("""
            INSERT INTO jurisdictions (display_name, level, state, country_code, parent_id, authority_type)
            SELECT 'Georgia', 'state', 'GA', 'US', :fed, 'geographic'
            WHERE NOT EXISTS (
                SELECT 1 FROM jurisdictions WHERE level = 'state' AND state = 'GA'
            )
        """),
        {"fed": fed_id},
    )


def upgrade() -> None:
    conn = op.get_bind()
    _ensure_missing_parents(conn)

    # 1. The plan: where every active row BELONGS. `target IS NULL` means we could
    #    not place it — those are left exactly where they are and reported. A
    #    guessed parent is worse than a known-misparented row, because it looks
    #    correct.
    conn.execute(text(f"""
        CREATE TEMP TABLE _jp_plan ON COMMIT DROP AS
        SELECT jr.id,
               jr.requirement_key,
               jr.jurisdiction_id AS cur,
               {_TARGET_SQL} AS target,
               COALESCE(jr.last_verified_at, jr.updated_at) AS freshness,
               jr.updated_at
        FROM jurisdiction_requirements jr
        JOIN jurisdictions cj ON cj.id = jr.jurisdiction_id
        WHERE jr.status = 'active'
    """))
    conn.execute(text("CREATE INDEX ON _jp_plan (target, requirement_key)"))
    conn.execute(text("CREATE INDEX ON _jp_plan (id)"))

    unplaceable = conn.execute(
        text("SELECT COUNT(*) FROM _jp_plan WHERE target IS NULL")).scalar()

    # 2. Winners and losers. For each (target, requirement_key) that will end up
    #    holding more than one row — whether those rows are already there or are
    #    moving in — keep the freshest and fold the rest into it. This is the
    #    same obligation, researched once per city.
    conn.execute(text("""
        CREATE TEMP TABLE _jp_merge ON COMMIT DROP AS
        WITH ranked AS (
            SELECT id, target, requirement_key,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY target, requirement_key
                       ORDER BY freshness DESC NULLS LAST, updated_at DESC NULLS LAST, id
                   ) AS winner,
                   ROW_NUMBER() OVER (
                       PARTITION BY target, requirement_key
                       ORDER BY freshness DESC NULLS LAST, updated_at DESC NULLS LAST, id
                   ) AS rn
            FROM _jp_plan
            WHERE target IS NOT NULL
        )
        SELECT id AS loser, winner FROM ranked WHERE rn > 1
    """))
    conn.execute(text("CREATE INDEX ON _jp_merge (loser)"))
    merged = conn.execute(text("SELECT COUNT(*) FROM _jp_merge")).scalar()

    # 3. Fold the losers into their winners: drop child rows that would violate a
    #    unique on repoint, repoint the rest, then delete the losers.
    for sql in _DEDUPE_BEFORE_REPOINT:
        conn.execute(text(sql))

    for tbl, col in _CHILD_FKS:
        conn.execute(text(f"""
            UPDATE {tbl} c SET {col} = m.winner
            FROM _jp_merge m WHERE c.{col} = m.loser
        """))

    conn.execute(text("""
        UPDATE jurisdiction_requirements jr SET superseded_by_id = m.winner
        FROM _jp_merge m WHERE jr.superseded_by_id = m.loser
    """))
    conn.execute(text("""
        DELETE FROM jurisdiction_requirements jr USING _jp_merge m WHERE jr.id = m.loser
    """))

    # 4. Move the survivors that are misparented.
    #
    #    canonical_key is NULLed on every moved row: it is jurisdiction-encoded
    #    (`oh_cleveland_…`) and UNIQUE, so after a move it names the jurisdiction
    #    the row came FROM. It is nullable and recomputed on next write — an
    #    absent identity is recoverable, a wrong one is not.
    moved = conn.execute(text("""
        UPDATE jurisdiction_requirements jr
        SET jurisdiction_id = p.target,
            canonical_key = NULL,
            updated_at = NOW()
        FROM _jp_plan p
        WHERE jr.id = p.id
          AND p.target IS NOT NULL
          AND p.target <> p.cur
          AND NOT EXISTS (SELECT 1 FROM _jp_merge m WHERE m.loser = jr.id)
    """)).rowcount

    # 5. Refresh the denormalized counts.
    conn.execute(text("""
        UPDATE jurisdictions j
        SET requirement_count = (
            SELECT COUNT(*) FROM jurisdiction_requirements r
            WHERE r.jurisdiction_id = j.id AND r.status = 'active'
        ), updated_at = NOW()
    """))

    # 6. Refuse to leave the catalog half-fixed.
    left = conn.execute(text(f"""
        SELECT COUNT(*) FROM jurisdiction_requirements jr
        JOIN jurisdictions cj ON cj.id = jr.jurisdiction_id
        WHERE jr.status = 'active' AND {_TARGET_SQL} IS NOT NULL
          AND {_TARGET_SQL} <> jr.jurisdiction_id
    """)).scalar()

    print(f"[jparent01] moved={moved} merged={merged} unplaceable={unplaceable} "
          f"still_misparented={left}")
    if left:
        raise RuntimeError(
            f"jparent01: {left} row(s) still misparented after the pass — refusing to "
            "leave the catalog half-fixed"
        )

    # Rehearsal hook. This migration DELETES ~1,000 catalog rows plus tenant-facing
    # compliance_requirements children, and has no downgrade — so there must be a
    # way to run the REAL code against the REAL data and see what it does without
    # keeping it. Alembic runs the upgrade in a transaction, so raising here rolls
    # back everything this pass did (and the revisions before it in the same run).
    # A transcribed .sql "equivalent" would be a second copy that could drift from
    # the code actually shipped; this cannot.
    #
    #     JPARENT_DRY_RUN=1 alembic upgrade jparent01
    if os.getenv("JPARENT_DRY_RUN") == "1":
        # RuntimeError, not SystemExit: SystemExit is a BaseException and not every
        # context manager in the stack unwinds it the same way. The abort must be
        # boring and certain.
        raise RuntimeError(
            f"[jparent01] DRY RUN — deliberately rolling back. Would have: "
            f"moved={moved} merged={merged} unplaceable={unplaceable} "
            f"still_misparented={left}"
        )


def downgrade() -> None:
    # Not reversible: the pre-migration state is most of the catalog unreachable
    # from its own jurisdiction chain, plus ~1,000 duplicate obligations that this
    # pass merged away. Restoring that is not a rollback, it is re-breaking.
    pass
