"""Heal rows whose stored write-identity no longer matches what the upsert computes.

`requirement_key` is the ON-CONFLICT identity, derived by `_compute_key_parts`
from category + rate_type + applicable_entity_types + title. When the stored
composite drifts from that derivation, the next research pass computes a
DIFFERENT identity, ON CONFLICT matches nothing, and a TWIN is minted — a second
active row for one obligation. That is precisely the polymorphy b694559 set out
to kill; it healed 469 composites but these escaped, because their drift is in
the entity-type prefix / category segment rather than the minimum_wage dialect:

    "Treatment Authorization Request (TAR)"
        stored:    payer_relations:prior_authorization_requirements
        computed:  medi_cal:payer_relations:prior_authorization_requirements
        (the row carries applicable_entity_types=['medi_cal'], which prefixes
         the identity — the stored composite predates that)

    "Statutory Maternity Leave" (London)
        stored:    sick_leave:statutory_maternity_leave
        computed:  leave:statutory_maternity_leave
        (already re-categorised to `leave`; the composite kept the old prefix)

Found by re-deriving the identity of every row rekey01 touched and diffing
against what is stored — a check worth keeping, because a re-key that leaves the
composite stale re-opens the collision it just closed on the very next research
pass.

Scope: rows carrying one of the keys rekey01 curated. Deliberately NOT a
registry-wide sweep — a blanket recompute would rewrite the identity of 2,600
rows on the strength of a derivation that has itself changed over time, and any
row whose target identity is already taken must be a merge decision, not a
silent overwrite. Those are SKIPPED and reported.

Idempotent: a row already in sync computes the same key and is left alone.

Revision ID: rekey02
Revises: rekey01
Create Date: 2026-07-14
"""
import json

from alembic import op
from sqlalchemy import text

revision = "rekey02"
down_revision = "rekey01"
branch_labels = None
depends_on = None

_KEYS = (
    "medicaid_provider_enrollment",
    "exempt_salary_threshold_regional",
    "statutory_maternity_leave",
    "prior_authorization_requirements",
    "state_quality_reporting_mandates",
)


def _entity_types(raw) -> list:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    return list(raw) if isinstance(raw, (list, tuple)) else []


def upgrade() -> None:
    from app.core.services.compliance_service import _compute_key_parts

    conn = op.get_bind()
    rows = conn.execute(
        text("""
            SELECT jr.id, jr.jurisdiction_id, jr.title, jr.category, jr.rate_type,
                   jr.regulation_key, jr.requirement_key, jr.jurisdiction_level,
                   jr.jurisdiction_name, jr.applicable_entity_types,
                   COALESCE(j.country_code, 'US') AS country_code
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.regulation_key = ANY(:keys)
              AND COALESCE(jr.status, 'active') = 'active'
        """),
        {"keys": list(_KEYS)},
    ).mappings().all()

    healed = skipped = 0
    for r in rows:
        req = {
            "category": r["category"],
            "title": r["title"],
            "jurisdiction_name": r["jurisdiction_name"],
            "jurisdiction_level": r["jurisdiction_level"],
            "country_code": r["country_code"],
            "rate_type": r["rate_type"],
            "regulation_key": r["regulation_key"],
            "applicable_entity_types": _entity_types(r["applicable_entity_types"]),
        }
        requirement_key, _bare = _compute_key_parts(req)
        if requirement_key == r["requirement_key"]:
            continue  # already in sync

        taken = conn.execute(
            text("""
                SELECT 1 FROM jurisdiction_requirements
                WHERE jurisdiction_id = :j AND requirement_key = :rk AND id <> :id
            """),
            {"j": r["jurisdiction_id"], "rk": requirement_key, "id": r["id"]},
        ).scalar()
        if taken:
            print(f"[rekey02] SKIP {r['title']!r} in {r['jurisdiction_name']}: "
                  f"target identity {requirement_key!r} already taken — merge decision")
            skipped += 1
            continue

        conn.execute(
            text("UPDATE jurisdiction_requirements "
                 "SET requirement_key = :rk, updated_at = NOW() WHERE id = :id"),
            {"rk": requirement_key, "id": r["id"]},
        )
        healed += 1

    print(f"[rekey02] healed {healed} drifted composite(s), skipped {skipped}")


def downgrade() -> None:
    # Not reversible: the pre-migration state is a stale identity that mints a
    # twin on the next research pass. Restoring it would restore the bug.
    pass
