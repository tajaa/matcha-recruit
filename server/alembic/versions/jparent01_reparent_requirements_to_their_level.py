"""Re-parent requirements to the jurisdiction whose level they claim.

THE BUG THIS FIXES
------------------
A requirement carries a *stamped* jurisdiction_level / jurisdiction_name, and
separately a jurisdiction_id FK to the node it hangs off. On 1,709 of 2,724
active rows (63%) these disagree — 1,157 rows stamped `state` hang off a CITY,
232 stamped `national` hang off a city, and so on.

Chain resolution (resolve_jurisdiction_stack) walks jurisdiction_id: city →
county → state → federal. So a row stamped "California / state" that physically
hangs off `Beverly Hills, CA` is **invisible to every other California city**.

That is not a cosmetic defect. Both "California State Minimum Wage" rows were
parented to city nodes (one to Beverly Hills, one to a junk `ca, CA` node), so a
Los Angeles tenant's Compliance tab served *zero* minimum-wage, overtime and
meal-break requirements. The law was in the catalog the whole time; the chain
just couldn't reach it.

Root causes in the write path (fixed alongside this migration in
compliance_service._resolve_jurisdiction_id_for_level):
  1. no `national` case  -> fell through "unknown level, treat as city"
  2. every failed parent lookup silently fell back to the leaf city
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
per city. 915 of the 1,663 moves collide that way; they are duplicates, not data
to lose.

A merge keeps the freshest row, repoints all 8 FK paths off the loser, and only
then deletes it. Three of those children carry uniques
(compliance_embeddings.requirement_id, uq_compliance_requirements_loc_jr,
scope_codifications(classification_id, jr_id)), so a repoint that would collide
drops the loser's child row instead of raising.

Two missing parents are created (France national, Georgia state). Rows we cannot
place are LEFT ALONE and reported — never guessed at. The junk `ca, CA` /
`FL, FL` nodes (a state code parsed as a city name) keep existing because live
business_locations point at them; re-homing a tenant's location is a separate,
human decision.

Idempotent: re-running finds nothing to move.

Revision ID: jparent01
Revises: rekey02
Create Date: 2026-07-14
"""
from alembic import op
from sqlalchemy import text

revision = "jparent01"
down_revision = "rekey02"
branch_labels = None
depends_on = None


# child table -> FK column. Repointed off a merge loser before it is deleted.
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

# Children with a unique that a repoint can violate: if the winner already has
# the conflicting row, the loser's row is redundant — drop it rather than raise.
_DEDUPE_BEFORE_REPOINT = {
    # unique (requirement_id)
    "compliance_embeddings": "DELETE FROM compliance_embeddings WHERE requirement_id = :loser "
                             "AND EXISTS (SELECT 1 FROM compliance_embeddings w WHERE w.requirement_id = :winner)",
    # unique (location_id, jurisdiction_requirement_id) WHERE jr_id IS NOT NULL
    "compliance_requirements": "DELETE FROM compliance_requirements l WHERE l.jurisdiction_requirement_id = :loser "
                               "AND EXISTS (SELECT 1 FROM compliance_requirements w "
                               "WHERE w.location_id = l.location_id AND w.jurisdiction_requirement_id = :winner)",
    # unique (classification_id, jurisdiction_requirement_id)
    "scope_codifications": "DELETE FROM scope_codifications l WHERE l.jurisdiction_requirement_id = :loser "
                           "AND EXISTS (SELECT 1 FROM scope_codifications w "
                           "WHERE w.classification_id = l.classification_id AND w.jurisdiction_requirement_id = :winner)",
}

# The target-parent resolver, as SQL. Kept in one place so the dry-run, the move
# and the post-check all agree on what "correct" means.
_TARGET_SQL = """
    CASE
      WHEN jr.jurisdiction_level IN ('federal','national') AND COALESCE(cj.country_code,'US') = 'US'
        THEN (SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' LIMIT 1)
      WHEN jr.jurisdiction_level IN ('federal','national')
        THEN (SELECT id FROM jurisdictions WHERE level = 'national' AND country_code = cj.country_code LIMIT 1)
      WHEN jr.jurisdiction_level = 'state'
        THEN (SELECT id FROM jurisdictions WHERE level = 'state' AND state = cj.state LIMIT 1)
      WHEN jr.jurisdiction_level = 'county'
        THEN (SELECT id FROM jurisdictions WHERE level = 'county'
                AND state = cj.state AND county = cj.county LIMIT 1)
      ELSE jr.jurisdiction_id
    END
"""


def _ensure_missing_parents(conn) -> None:
    """Create the two parents the data needs but the tree lacks.

    18 French national rows hang off `Paris, IDF, FR` and 12 Georgia state rows
    hang off `atlanta, GA` purely because no France / Georgia node exists.
    """
    conn.execute(text("""
        INSERT INTO jurisdictions (display_name, level, country_code, authority_type)
        SELECT 'France', 'national', 'FR', 'geographic'
        WHERE NOT EXISTS (
            SELECT 1 FROM jurisdictions WHERE level = 'national' AND country_code = 'FR'
        )
    """))
    fed_id = conn.execute(
        text("SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' LIMIT 1")
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


def _merge(conn, winner, loser) -> None:
    """Fold `loser` into `winner`: repoint every child, then delete."""
    for tbl, sql in _DEDUPE_BEFORE_REPOINT.items():
        conn.execute(text(sql), {"loser": loser, "winner": winner})
    for tbl, col in _CHILD_FKS:
        conn.execute(
            text(f"UPDATE {tbl} SET {col} = :winner WHERE {col} = :loser"),
            {"winner": winner, "loser": loser},
        )
    conn.execute(
        text("UPDATE jurisdiction_requirements SET superseded_by_id = :winner "
             "WHERE superseded_by_id = :loser"),
        {"winner": winner, "loser": loser},
    )
    conn.execute(
        text("DELETE FROM jurisdiction_requirements WHERE id = :loser"), {"loser": loser}
    )


def upgrade() -> None:
    conn = op.get_bind()
    _ensure_missing_parents(conn)

    rows = conn.execute(text(f"""
        SELECT jr.id, jr.requirement_key, jr.jurisdiction_id AS cur,
               jr.last_verified_at, jr.updated_at,
               {_TARGET_SQL} AS target
        FROM jurisdiction_requirements jr
        JOIN jurisdictions cj ON cj.id = jr.jurisdiction_id
        WHERE jr.status = 'active'
    """)).mappings().all()

    moved = merged = unplaceable = 0
    for r in rows:
        target = r["target"]
        if target is None:
            # No node to hang it on and no safe way to invent one. Leave it
            # exactly where it is and report — a guessed parent is worse than a
            # known-misparented row, because it looks correct.
            unplaceable += 1
            continue
        if target == r["cur"]:
            continue

        rival = conn.execute(
            text("""
                SELECT id, last_verified_at, updated_at
                FROM jurisdiction_requirements
                WHERE jurisdiction_id = :t AND requirement_key = :k
                  AND status = 'active' AND id <> :id
                LIMIT 1
            """),
            {"t": target, "k": r["requirement_key"], "id": r["id"]},
        ).mappings().first()

        if rival is None:
            conn.execute(
                text("UPDATE jurisdiction_requirements "
                     "SET jurisdiction_id = :t, updated_at = NOW() WHERE id = :id"),
                {"t": target, "id": r["id"]},
            )
            moved += 1
            continue

        # Same obligation, two homes: the state law was re-researched per city.
        # Keep the freshest content; the survivor must end up at `target`.
        def _stamp(x):
            return (x["last_verified_at"] or x["updated_at"], x["updated_at"])

        if _stamp(r) > _stamp(rival):
            # The misparented row is fresher: fold the rival into it, then move it.
            _merge(conn, winner=r["id"], loser=rival["id"])
            conn.execute(
                text("UPDATE jurisdiction_requirements "
                     "SET jurisdiction_id = :t, updated_at = NOW() WHERE id = :id"),
                {"t": target, "id": r["id"]},
            )
        else:
            _merge(conn, winner=rival["id"], loser=r["id"])
        merged += 1

    conn.execute(text("""
        UPDATE jurisdictions j
        SET requirement_count = (
            SELECT COUNT(*) FROM jurisdiction_requirements r
            WHERE r.jurisdiction_id = j.id AND r.status = 'active'
        ), updated_at = NOW()
    """))

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


def downgrade() -> None:
    # Not reversible: the pre-migration state is 63% of the catalog unreachable
    # from its own jurisdiction chain, plus ~900 duplicate obligations that this
    # pass merged away. Restoring that is not a rollback, it is re-breaking.
    pass
