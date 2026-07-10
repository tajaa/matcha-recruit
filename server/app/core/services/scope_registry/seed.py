"""Phase-1 seed classifications — citation-anchored, provisional, gated.

Accelerates authoring for the citations we actually ingest (commit 3's federal
parts + curated CA slices). Seed provenance is LLM-authored judgment
(`industry_keysets` + the curated slices), which is why every row lands
``provisional`` and requires human confirmation — the seed accelerates
authoring; it does not grant authority (plan §10).

Every proposal passes the same :func:`classify.validate_proposal` gates as a
Gemini proposal. Regulation keys are cited only where
`regulation_key_definitions` actually holds them (checked at apply time —
an absent key degrades to NULL/uncodified with a warning, never invented).

Conditional attribute keys used here and their provenance:
  * ``employee_count`` — the established runtime-injected roster attribute
    (`matcha_work_node.py` injects it into facility_attributes), so FMLA's
    ≥50 threshold evaluates deterministically.
  * ``psm_covered_chemicals`` — boolean facility attribute meaning "holds a
    29 CFR 1910.119 Appendix A chemical above its threshold quantity".
    Documented here as the canonical spelling; authored per-location.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .classify import fetch_rkd_keys_by_category, validate_proposal

_FMLA_CONDITION = {
    "type": "attribute", "key": "employee_count", "operator": "gte", "value": 50,
}
_PSM_CONDITION = {
    "type": "attribute", "key": "psm_covered_chemicals", "operator": "eq", "value": True,
}


def _universal(category_slug: str | None = None, regulation_key: str | None = None) -> Dict[str, Any]:
    return {
        "disposition": "universal_in_domain",
        "applies_to_categories": [],
        "excludes_categories": [],
        "regulation_key": regulation_key,
        "category_slug": category_slug,
    }


def _category(applies_to: List[str], regulation_key: str | None = None,
              category_slug: str | None = None) -> Dict[str, Any]:
    return {
        "disposition": "category_specific",
        "applies_to_categories": applies_to,
        "excludes_categories": [],
        "regulation_key": regulation_key,
        "category_slug": category_slug,
    }


def _conditional(condition: Dict[str, Any], applies_to: List[str] | None = None,
                 regulation_key: str | None = None, category_slug: str | None = None) -> Dict[str, Any]:
    return {
        "disposition": "conditional",
        "applies_to_categories": applies_to or [],
        "excludes_categories": [],
        "entity_condition": condition,
        "regulation_key": regulation_key,
        "category_slug": category_slug,
    }


# citation → proposal. ONLY citations the commit-3 ingest actually produces:
# curated CA rows verbatim from curated_ca.CURATED_ROWS; federal subpart
# citations in authority_parse's "29 CFR {part} Subpart {X}" form.
SEED_CLASSIFICATIONS: Dict[str, Dict[str, Any]] = {
    # ── ca-labor-code: AB 701 — warehouse quotas (the taxonomy-split proof) ──
    "Cal. Lab. Code § 2100": _category(["warehousing"]),
    "Cal. Lab. Code § 2101": _category(["warehousing"]),
    "Cal. Lab. Code § 2102": _category(["warehousing"]),
    "Cal. Lab. Code § 2103": _category(["warehousing"]),
    "Cal. Lab. Code § 2104": _category(["warehousing"]),
    "Cal. Lab. Code § 2105": _category(["warehousing"]),
    # ── ca-title-8: Cal/OSHA core (all CA employers in general industry) ──
    "8 CCR § 3203": _universal(category_slug="workplace_safety"),
    "8 CCR § 3204": _universal(category_slug="workplace_safety"),
    "8 CCR § 3395": _universal(category_slug="workplace_safety"),
    "8 CCR § 3396": _universal(category_slug="workplace_safety"),
    "8 CCR § 5194": _universal(category_slug="chemical_safety"),
    "8 CCR § 5199": _category(["healthcare"], category_slug="clinical_safety"),
    # ── ca-title-16: optometry/opticianry board — ophthalmology practices ──
    "Cal. Bus. & Prof. Code § 3041": _category(["ophthalmology"]),
    "Cal. Bus. & Prof. Code § 3041.3": _category(["ophthalmology"]),
    "16 CCR § 1536": _category(["ophthalmology"]),
    "Cal. Bus. & Prof. Code § 2542": _category(["ophthalmology"]),
    "Cal. Bus. & Prof. Code § 2550": _category(["ophthalmology"]),
    # ── 29 CFR 825 (FMLA): conditional on headcount, everyone in domain ──
    "29 CFR 825 Subpart A": _conditional(_FMLA_CONDITION, regulation_key="fmla",
                                         category_slug="leave"),
    "29 CFR 825 Subpart B": _conditional(_FMLA_CONDITION, category_slug="leave"),
    "29 CFR 825 Subpart C": _conditional(_FMLA_CONDITION, category_slug="leave"),
    # ── 29 CFR 1904 (injury/illness recordkeeping): universal ──
    # (partial-exemption NAICS list is a per-section refinement for later)
    "29 CFR 1904 Subpart A": _universal(category_slug="workplace_safety"),
    "29 CFR 1904 Subpart C": _universal(
        category_slug="workplace_safety",
        regulation_key="injury_illness_recordkeeping",
    ),
    "29 CFR 1904 Subpart D": _universal(category_slug="workplace_safety"),
    "29 CFR 1904 Subpart E": _universal(category_slug="workplace_safety"),
    # ── 29 CFR 1910: the two plan-exemplar sections ──
    # Subpart-level Gemini classification covers the rest; these two pin the
    # acceptance tests (1910.147 in for a warehouse, 1910.119 conditional).
    "29 CFR 1910.147": _universal(category_slug="machine_safety"),
    "29 CFR 1910.119": _conditional(_PSM_CONDITION, category_slug="process_safety"),
}


async def apply_seed(conn) -> Dict[str, Any]:
    """Apply the seed to whatever ingested items exist. Idempotent.

    Missing citations are reported, not errors — the seed is written against
    the full commit-3 catalog, but an admin may ingest indexes one at a time.
    """
    from .classify import (
        _refresh_unclassified_count,
        _upsert_classification,
        materialize_inherited_children,
    )

    rkd = await fetch_rkd_keys_by_category(conn)
    applied = 0
    missing: List[str] = []
    warnings: List[str] = []
    touched_indexes = set()

    for citation, proposal in SEED_CLASSIFICATIONS.items():
        normalized, item_warnings = validate_proposal(proposal, rkd)
        warnings.extend(f"{citation}: {w}" for w in item_warnings)
        if normalized is None:
            # A seed row failing hard gates is a bug in this file, not data.
            raise ValueError(f"seed proposal for {citation!r} is invalid: {item_warnings}")

        row = await conn.fetchrow(
            "SELECT id, authority_index_id FROM authority_index_items WHERE citation = $1",
            citation,
        )
        if row is None:
            missing.append(citation)
            continue

        # Never overwrite an existing classification — the seed yields to both
        # Gemini proposals an admin is reviewing and confirmed human decisions.
        existing = await conn.fetchval(
            "SELECT 1 FROM authority_item_classifications WHERE item_id = $1", row["id"]
        )
        if existing:
            continue

        await _upsert_classification(
            conn, row["id"], normalized, proposed_by="seed", status="provisional"
        )
        touched_indexes.add(row["authority_index_id"])
        applied += 1

    # Seeding a subpart leaves its ingested child sections unclassified —
    # materialize their inheritance now or they're unreachable (classify only
    # targets unclassified items, and these have classified parents).
    inherited = 0
    for index_id in touched_indexes:
        inherited += await materialize_inherited_children(conn, index_id)
        await _refresh_unclassified_count(conn, index_id)

    return {
        "applied": applied,
        "inherited": inherited,
        "missing_citations": missing,
        "warnings": warnings,
    }
