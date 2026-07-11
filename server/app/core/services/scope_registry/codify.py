"""The codify layer — the explicit link between SCOPE and STORE.

`resolve_scope`/`labor_scope` call an obligation "codified" by matching the
scope classification's `regulation_key` against a `jurisdiction_requirements`
row — a string join recomputed on every read. This module records that match as
a stored fact (`scope_codifications`) with provenance, and (commit 3) drives the
fetch queue into research so the loop closes.

`match_codifications` is the pure core (key equality + a category guard);
`reconcile_codifications` fetches, matches, and upserts the linkage.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .jurisdiction_chain import resolve_jurisdiction_chain

logger = logging.getLogger(__name__)


def match_codifications(
    classifications: List[Dict[str, Any]],
    requirement_rows: List[Dict[str, Any]],
    rkd_category_by_id: Optional[Dict[Any, str]] = None,
) -> List[Dict[str, Any]]:
    """Key-equality join between confirmed classifications and catalog rows (pure).

    One linkage per (classification × requirement) sharing a non-NULL
    ``regulation_key``. When the classification carries a ``key_definition_id``,
    the requirement's ``category`` must also equal that key's RKD ``category_slug``
    — guards the same key living in two categories (e.g. ``exempt_salary_threshold``
    under both minimum_wage and overtime).

    ``classifications``: rows with ``id``, ``regulation_key``, ``key_definition_id``.
    ``requirement_rows``: rows with ``id``, ``regulation_key``, ``jurisdiction_id``,
    ``category``.
    """
    rkd_category_by_id = rkd_category_by_id or {}

    reqs_by_key: Dict[str, List[Dict[str, Any]]] = {}
    for r in requirement_rows:
        key = r.get("regulation_key")
        if key:
            reqs_by_key.setdefault(key, []).append(r)

    links: List[Dict[str, Any]] = []
    for c in classifications:
        key = c.get("regulation_key")
        if not key:
            continue  # NULL-key classifications can never codify
        want_category = rkd_category_by_id.get(c.get("key_definition_id"))
        for r in reqs_by_key.get(key, []):
            if want_category is not None and r.get("category") != want_category:
                continue
            links.append({
                "classification_id": c["id"],
                "jurisdiction_requirement_id": r["id"],
                "regulation_key": key,
                "jurisdiction_id": r.get("jurisdiction_id"),
            })
    return links


# Registry source_type / slug heuristics for the regulation-over-statute rule.
# The regulation carries the operative value (29 CFR 541.600 states the dollar
# amount; 29 U.S.C. 213 only authorizes the exemption), so it's the citation an
# admin should re-check first.
def _is_regulation_citation(citation: str, source_type: Optional[str]) -> bool:
    c = (citation or "").upper()
    if " CFR " in c or " CCR " in c or "TITLE 8" in c or "TITLE 16" in c:
        return True
    if " U.S.C" in c or " USC " in c or "LAB. CODE" in c or "LABOR CODE" in c:
        return False
    # curated regulatory indexes (ca-title-8/16) vs statutory (us-flsa, ca-labor-code)
    return (source_type or "") == "ecfr"


def _hierarchy_depth(hierarchy: Any) -> int:
    """How specific the citation is — section beats subpart beats part. Pure."""
    if isinstance(hierarchy, str):
        try:
            hierarchy = json.loads(hierarchy)
        except (ValueError, TypeError):
            return 0
    if not isinstance(hierarchy, dict):
        return 0
    return sum(1 for k in ("title", "part", "subpart", "section") if hierarchy.get(k))


def select_primary_citation(
    candidates: List[Dict[str, Any]], *, requirement_level: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Pick the one citation that goes in ``statute_citation`` when several
    classifications codify the same requirement key. Pure + deterministic.

    Each candidate: ``{item_id, citation, hierarchy, index_slug, source_type,
    jurisdiction_level}``. Precedence (highest first):
      1. authority index jurisdiction level matches the requirement's level
         (a state row's citation should be the state code, not federal CFR).
      2. regulation over statute (the regulation carries the operative value).
      3. deepest hierarchy (section > subpart > part).
      4. lexicographic citation (stable tie-break for tests).
    """
    if not candidates:
        return None
    want_level = (requirement_level or "").lower()

    def sort_key(c: Dict[str, Any]):
        level_match = (c.get("jurisdiction_level") or "").lower() == want_level and bool(want_level)
        return (
            0 if level_match else 1,
            0 if _is_regulation_citation(c.get("citation", ""), c.get("source_type")) else 1,
            -_hierarchy_depth(c.get("hierarchy")),
            c.get("citation") or "",
        )

    return sorted(candidates, key=sort_key)[0]


def _authority_governs(link: Dict[str, Any], req_state: Optional[str]) -> bool:
    """A citation may stamp a requirement only if its authority actually governs
    that jurisdiction: federal authorities (no jurisdiction) govern everyone; a
    state/local authority governs only same-state requirements. Without this a
    key-equality codification link would let e.g. Cal. Lab. Code stamp an Arizona
    row (match_codifications is jurisdiction-blind by design)."""
    if link.get("authority_jurisdiction_id") is None:
        return True  # federal / global
    astate = (link.get("authority_state") or "").upper()
    rstate = (req_state or "").upper()
    return bool(astate) and astate == rstate


def build_citation_stamps(
    links: List[Dict[str, Any]],
    requirement_meta: Optional[Dict[Any, Dict[str, Any]]] = None,
) -> Dict[Any, Dict[str, Any]]:
    """Collapse per-(classification×requirement) links carrying item metadata into
    a per-requirement stamp: the primary ``statute_citation`` + ``citation_item_id``
    plus the full ``verified_citations`` set for ``metadata``. Pure.

    Each link must carry ``jurisdiction_requirement_id`` and item/authority fields
    (``item_id``, ``citation``, ``hierarchy``, ``index_slug``, ``source_type``,
    ``jurisdiction_level``, ``authority_jurisdiction_id``, ``authority_state``).
    ``requirement_meta`` maps requirement id → ``{level, state}`` — ``level`` drives
    the primary-citation tie-break, ``state`` the jurisdiction guard.
    """
    requirement_meta = requirement_meta or {}
    by_req: Dict[Any, List[Dict[str, Any]]] = {}
    for link in links:
        rid = link.get("jurisdiction_requirement_id")
        if rid is None or not link.get("item_id") or not link.get("citation"):
            continue
        if not _authority_governs(link, (requirement_meta.get(rid) or {}).get("state")):
            continue  # a state authority can't codify another state's row
        by_req.setdefault(rid, []).append(link)

    stamps: Dict[Any, Dict[str, Any]] = {}
    for rid, cands in by_req.items():
        # de-dupe on item_id (same citation reached via two classifications)
        seen: Dict[Any, Dict[str, Any]] = {}
        for c in cands:
            seen.setdefault(c["item_id"], c)
        uniq = list(seen.values())
        primary = select_primary_citation(
            uniq, requirement_level=(requirement_meta.get(rid) or {}).get("level"))
        if primary is None:
            continue
        verified = sorted(
            (
                {"citation": c["citation"], "item_id": str(c["item_id"]),
                 "index_slug": c.get("index_slug")}
                for c in uniq
            ),
            key=lambda v: v["citation"],
        )
        stamps[rid] = {
            "statute_citation": primary["citation"],
            "citation_item_id": primary["item_id"],
            "verified_citations": verified,
        }
    return stamps


async def chain_uncodified(
    conn, *, state: Optional[str] = None, city: Optional[str] = None,
    labor_only: bool = True,
) -> Dict[str, Any]:
    """The chain's research worklist: confirmed applicable classifications with no
    codified value in the chain, split into ``keyed`` (researchable — has a
    regulation_key to codify against) and ``unkeyed`` (NULL key — needs a key
    minted before research can codify it).

    ``state`` optional: federal-only chain when absent (mirrors labor_scope).
    ``labor_only`` restricts to labor-domain indexes so the worklist matches
    what the Labor scope panel shows (the surface that triggers research).

    Returns ``{chain, keyed: [...], unkeyed: [...]}``. Each keyed item carries
    ``classification_id``, ``regulation_key``, ``category_slug`` (RKD), ``level``,
    ``citation``, ``heading``.
    """
    from .resolve import classification_matches
    from .labor_scope import is_labor_index

    if state and state.strip():
        jur = await resolve_jurisdiction_chain(conn, state.strip().upper(), city)
    else:
        federal = await conn.fetchval(
            "SELECT id FROM jurisdictions WHERE level::text = 'federal' LIMIT 1"
        )
        jur = {"ids": [federal] if federal else [], "state_found": False,
               "city_found": False, "federal_id": federal, "state_id": None, "city_id": None}
    ids = jur["ids"]

    rows = [
        dict(r) for r in await conn.fetch(
            """
            SELECT c.id AS classification_id, c.disposition, c.applies_to_categories,
                   c.excludes_categories, c.entity_condition, c.regulation_key,
                   c.key_definition_id, rkd.category_slug,
                   i.id AS item_id, i.citation, i.heading,
                   (i.body_text IS NOT NULL) AS has_body,
                   ai.level, ai.slug AS index_slug,
                   ai.domain_categories
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            LEFT JOIN regulation_key_definitions rkd ON rkd.id = c.key_definition_id
            WHERE c.status = 'confirmed' AND c.disposition <> 'excluded'
              AND (ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY($1::uuid[]))
            """,
            ids,
        )
    ]
    if labor_only:
        rows = [r for r in rows if is_labor_index(r["index_slug"], r["domain_categories"])]

    # Generic-employer applicability (empty chain + attrs): universal matches,
    # category_specific/conditional don't — the same set the panel shows.
    applicable = [r for r in rows if classification_matches(r, [], {})]

    # Codified keys already present in the chain.
    codified_keys = set(await conn.fetchval(
        """
        SELECT COALESCE(array_agg(DISTINCT regulation_key), '{}')
        FROM jurisdiction_requirements
        WHERE jurisdiction_id = ANY($1::uuid[])
          AND regulation_key IS NOT NULL
          AND COALESCE(status, 'active') = 'active'
        """,
        ids,
    ) or [])

    keyed, unkeyed = [], []
    for r in applicable:
        item = {
            "classification_id": r["classification_id"],
            "regulation_key": r["regulation_key"],
            "category_slug": r["category_slug"],
            "level": r["level"],
            "citation": r["citation"],
            "heading": r["heading"],
            "item_id": r["item_id"],
            "index_slug": r["index_slug"],
            "has_body": r["has_body"],
        }
        if not r["regulation_key"]:
            unkeyed.append(item)
        elif r["regulation_key"] not in codified_keys:
            keyed.append(item)
    return {
        "chain": {"federal_id": jur["federal_id"], "state_id": jur["state_id"],
                  "city_id": jur["city_id"], "state_found": jur["state_found"],
                  "city_found": jur["city_found"]},
        "keyed": keyed,
        "unkeyed": unkeyed,
    }


def build_research_context(items: List[Dict[str, Any]]) -> str:
    """Target the specific missed obligations in the Gemini research prompt."""
    lines = []
    for it in items:
        cite = it.get("citation") or ""
        heading = it.get("heading") or ""
        key = it.get("regulation_key") or ""
        lines.append(f"- {key} ({cite}{' — ' + heading if heading else ''})")
    return (
        "Target these specific obligations that are in scope but not yet codified "
        "for this jurisdiction:\n" + "\n".join(lines)
    )


def group_research_units(
    keyed_items: List[Dict[str, Any]],
    *,
    federal_id: Any,
    state_id: Any,
    city_id: Any,
) -> List[Dict[str, Any]]:
    """Group keyed worklist items into (target jurisdiction × category) research
    units. Level → target: federal→federal_id, state→state_id, city/county/local→
    city_id (falls back to state_id when there's no city row). Items whose target
    jurisdiction can't be resolved are dropped (reported by the caller). Pure."""
    def target(level: str) -> Any:
        lvl = (level or "").lower()
        if lvl == "federal":
            return federal_id
        if lvl in ("city", "county", "local", "special_district"):
            return city_id or state_id
        return state_id

    by_jur: Dict[Any, Dict[str, Any]] = {}
    for it in keyed_items:
        jid = target(it["level"])
        if not jid or not it.get("category_slug"):
            continue  # no target jurisdiction row, or no RKD category to research
        unit = by_jur.setdefault(jid, {"jurisdiction_id": jid, "categories": set(),
                                       "keys": [], "items": []})
        unit["categories"].add(it["category_slug"])
        unit["keys"].append(it["regulation_key"])
        unit["items"].append(it)

    units = []
    for unit in by_jur.values():
        units.append({
            "jurisdiction_id": unit["jurisdiction_id"],
            "categories": sorted(unit["categories"]),
            "keys": unit["keys"],
            "items": unit["items"],
            "context": build_research_context(unit["items"]),
        })
    return units


def affected_requirement_updates(
    drift_rows: List[Dict[str, Any]],
    codification_links: List[Dict[str, Any]],
) -> Dict[Any, Dict[str, Any]]:
    """Map authority drift → the requirement rows whose codified value it puts in
    doubt. Pure.

    ``drift_rows``: ``{drift_id, change_type, citation, detected_at,
    authority_index_id}``. Only ``amended``/``removed`` propagate — a ``new``
    citation has no classification yet, so it can't join to any requirement (it
    stays a drift-queue-only "go classify this" signal).

    ``codification_links``: the resolved item→classification→codification join,
    ``{authority_index_id, citation, requirement_id, prior_change_status}``.

    Returns ``{requirement_id: {drift_id, change_type, citation, detected_at,
    prior_change_status}}`` — one entry per requirement, latest ``detected_at``
    winning when two drift rows hit the same row.
    """
    links_by_key: Dict[tuple, List[Dict[str, Any]]] = {}
    for link in codification_links:
        links_by_key.setdefault(
            (link.get("authority_index_id"), link.get("citation")), []
        ).append(link)

    def _dt_key(v):
        # None can't occur in practice (detected_at is NOT NULL DEFAULT NOW()),
        # but keep the pure fn sound: a real datetime must never be compared to 0.
        return v if v is not None else datetime.min

    updates: Dict[Any, Dict[str, Any]] = {}
    for d in drift_rows:
        if d.get("change_type") not in ("amended", "removed"):
            continue
        key = (d.get("authority_index_id"), d.get("citation"))
        for link in links_by_key.get(key, []):
            rid = link.get("requirement_id")
            if rid is None:
                continue
            candidate = {
                "drift_id": d.get("drift_id"),
                "change_type": d.get("change_type"),
                "citation": d.get("citation"),
                "detected_at": d.get("detected_at"),
                "prior_change_status": link.get("prior_change_status"),
            }
            existing = updates.get(rid)
            if existing is None or _dt_key(candidate["detected_at"]) >= _dt_key(existing["detected_at"]):
                updates[rid] = candidate
    return updates


async def propagate_drift_to_requirements(conn) -> Dict[str, Any]:
    """Fan unpropagated amended/removed drift out to the requirement rows whose
    value is codified from the drifted citation: flag ``change_status =
    'needs_review'`` + a ``metadata.drift`` breadcrumb, then stamp
    ``propagated_at`` on every processed drift row (idempotent — reruns are no-ops).

    Runs after ingest completes (a changed authority makes its codified values
    suspect immediately, before anyone acknowledges the drift). Returns counts.
    """
    drift_rows = [
        dict(r) for r in await conn.fetch(
            """
            SELECT id AS drift_id, authority_index_id, change_type, citation, detected_at
            FROM authority_index_drift
            WHERE propagated_at IS NULL AND change_type IN ('amended', 'removed')
            """
        )
    ]
    if not drift_rows:
        # Still stamp any unpropagated 'new' rows so they don't re-scan forever.
        marked = await conn.fetchval(
            """
            WITH u AS (
                UPDATE authority_index_drift SET propagated_at = NOW()
                WHERE propagated_at IS NULL RETURNING 1
            ) SELECT COUNT(*) FROM u
            """
        )
        return {"drift_processed": int(marked or 0), "requirements_flagged": 0}

    # Resolve the join: drifted citation → item → classification → codification →
    # requirement (the stored linkage, not a raw key match which would over-flag).
    index_ids = list({d["authority_index_id"] for d in drift_rows})
    citations = list({d["citation"] for d in drift_rows})
    links = [
        dict(r) for r in await conn.fetch(
            """
            SELECT i.authority_index_id, i.citation,
                   sc.jurisdiction_requirement_id AS requirement_id,
                   -- Preserve the ORIGINAL pre-drift status across cascading drift:
                   -- once a row is already needs_review from an earlier drift, its
                   -- live change_status is 'needs_review' (only this path sets it),
                   -- so snapshotting it would overwrite the true restore target. The
                   -- first drift's breadcrumb already holds the real prior status.
                   COALESCE(jr.metadata->'drift'->>'prior_change_status',
                            jr.change_status) AS prior_change_status
            FROM authority_index_items i
            JOIN authority_item_classifications c ON c.item_id = i.id
            JOIN scope_codifications sc ON sc.classification_id = c.id
            JOIN jurisdiction_requirements jr ON jr.id = sc.jurisdiction_requirement_id
            WHERE i.authority_index_id = ANY($1::uuid[]) AND i.citation = ANY($2::text[])
            """,
            index_ids, citations,
        )
    ]

    updates = affected_requirement_updates(drift_rows, links)

    # Flag the affected requirements and stamp propagated_at as one atomic unit:
    # if the flag succeeds but the stamp doesn't, the next ingest re-processes the
    # same drift and re-snapshots the (now needs_review) status — the corruption
    # the COALESCE above defends against. Keeping both writes in one transaction
    # closes that window.
    flagged = 0
    async with conn.transaction():
        if updates:
            req_ids = list(updates.keys())
            breadcrumbs = [
                json.dumps({"drift": {
                    "drift_id": str(updates[r]["drift_id"]),
                    "change_type": updates[r]["change_type"],
                    "citation": updates[r]["citation"],
                    "detected_at": (updates[r]["detected_at"].isoformat()
                                    if hasattr(updates[r]["detected_at"], "isoformat")
                                    else updates[r]["detected_at"]),
                    "prior_change_status": updates[r]["prior_change_status"],
                }})
                for r in req_ids
            ]
            flagged = await conn.fetchval(
                """
                WITH u AS (
                    UPDATE jurisdiction_requirements AS jr
                    SET change_status = 'needs_review',
                        metadata = COALESCE(jr.metadata, '{}'::jsonb) || t.crumb::jsonb,
                        updated_at = NOW()
                    FROM unnest($1::uuid[], $2::jsonb[]) AS t(req_id, crumb)
                    WHERE jr.id = t.req_id
                    RETURNING 1
                ) SELECT COUNT(*) FROM u
                """,
                req_ids, breadcrumbs,
            )

        # Stamp every unpropagated drift row (amended/removed we just processed,
        # plus any 'new' rows) so the worklist drains.
        processed = await conn.fetchval(
            """
            WITH u AS (
                UPDATE authority_index_drift SET propagated_at = NOW()
                WHERE propagated_at IS NULL RETURNING 1
            ) SELECT COUNT(*) FROM u
            """
        )
    return {"drift_processed": int(processed or 0), "requirements_flagged": int(flagged or 0)}


async def reconcile_codifications(
    conn,
    *,
    state: Optional[str] = None,
    city: Optional[str] = None,
    source: str = "reconcile",
    run_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Match confirmed keyed classifications against keyed catalog rows and
    persist the linkage. Chain-scoped when ``state`` is given, else registry-wide.

    Returns counts: ``classifications_checked``, ``matched`` (link pairs),
    ``inserted``, ``updated``, ``unmatched_keys`` (keyed classifications with no
    catalog match — vocabulary drift / genuinely uncodified).
    """
    if state and state.strip():
        jur = await resolve_jurisdiction_chain(conn, state.strip().upper(), city)
        chain_ids = jur["ids"]
    else:
        chain_ids = None

    # Confirmed, non-excluded, keyed classifications (chain-filtered on the
    # authority index's jurisdiction; federal/global indexes always included).
    class_where = ["c.status = 'confirmed'", "c.disposition <> 'excluded'",
                   "c.regulation_key IS NOT NULL"]
    class_params: List[Any] = []
    if chain_ids is not None:
        class_params.append(chain_ids)
        class_where.append(
            f"(ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY(${len(class_params)}::uuid[]))"
        )
    classifications = [
        dict(r) for r in await conn.fetch(
            f"""
            SELECT c.id, c.regulation_key, c.key_definition_id,
                   i.id AS item_id, i.citation, i.hierarchy,
                   ai.slug AS index_slug, ai.source_type, ai.level AS jurisdiction_level,
                   ai.jurisdiction_id AS authority_jurisdiction_id,
                   aij.state AS authority_state
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            LEFT JOIN jurisdictions aij ON aij.id = ai.jurisdiction_id
            WHERE {' AND '.join(class_where)}
            """,
            *class_params,
        )
    ]

    # Active keyed catalog rows (chain-filtered on the requirement's jurisdiction).
    req_where = ["jr.regulation_key IS NOT NULL", "COALESCE(jr.status, 'active') = 'active'"]
    req_params: List[Any] = []
    if chain_ids is not None:
        req_params.append(chain_ids)
        req_where.append(f"jr.jurisdiction_id = ANY(${len(req_params)}::uuid[])")
    requirement_rows = [
        dict(r) for r in await conn.fetch(
            f"""
            SELECT jr.id, jr.regulation_key, jr.jurisdiction_id, jr.category,
                   jr.jurisdiction_level, jr.statute_citation, jr.citation_verified_at,
                   j.state AS requirement_state
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {' AND '.join(req_where)}
            """,
            *req_params,
        )
    ]

    # RKD category per key_definition_id, so the matcher can enforce the guard.
    kd_ids = sorted({c["key_definition_id"] for c in classifications if c.get("key_definition_id")})
    rkd_category_by_id: Dict[Any, str] = {}
    if kd_ids:
        for r in await conn.fetch(
            "SELECT id, category_slug FROM regulation_key_definitions WHERE id = ANY($1::uuid[])",
            kd_ids,
        ):
            rkd_category_by_id[r["id"]] = r["category_slug"]

    links = match_codifications(classifications, requirement_rows, rkd_category_by_id)

    run_info_json = json.dumps(run_info) if run_info else None

    # Build the verified-citation stamps in Python first (pure, no DB), so the
    # three writes below can form one tight transaction.
    #
    # The citation comes from the classification's authority_index_item — verified
    # by construction, never from model free-recall. Registry wins over a
    # hand-edited citation (the overwrite is counted, not silent).
    class_meta = {c["id"]: c for c in classifications}
    req_meta = {
        r["id"]: {"level": r.get("jurisdiction_level"), "state": r.get("requirement_state")}
        for r in requirement_rows
    }
    # A prior manual citation = citation present but never registry-verified.
    manual_before = {
        r["id"] for r in requirement_rows
        if r.get("statute_citation") and r.get("citation_verified_at") is None
    }
    prior_citation_by_id = {r["id"]: r.get("statute_citation") for r in requirement_rows}
    stamp_links = []
    for link in links:
        meta = class_meta.get(link["classification_id"], {})
        stamp_links.append({**link, **{
            "item_id": meta.get("item_id"),
            "citation": meta.get("citation"),
            "hierarchy": meta.get("hierarchy"),
            "index_slug": meta.get("index_slug"),
            "source_type": meta.get("source_type"),
            "jurisdiction_level": meta.get("jurisdiction_level"),
            "authority_jurisdiction_id": meta.get("authority_jurisdiction_id"),
            "authority_state": meta.get("authority_state"),
        }})
    stamps = build_citation_stamps(stamp_links, req_meta)
    stamped_ids = list(stamps.keys())

    inserted = updated = 0
    citations_stamped = 0
    overwrote_manual = 0
    cleared = 0
    # Insert the linkage, stamp verified citations, and self-correct stale stamps
    # as one atomic unit — a partial run must never leave codifications inserted
    # but citations unstamped, or new stamps written while stale ones aren't
    # cleared (that inconsistency is exactly what a re-run would then act on).
    async with conn.transaction():
        if links:
            # One set-based upsert (unnest) instead of N round trips.
            result = await conn.fetch(
                """
                INSERT INTO scope_codifications
                    (classification_id, jurisdiction_requirement_id, regulation_key,
                     jurisdiction_id, source, run_info)
                SELECT * FROM unnest(
                    $1::uuid[], $2::uuid[], $3::text[], $4::uuid[]
                ) AS t(classification_id, jurisdiction_requirement_id, regulation_key, jurisdiction_id),
                LATERAL (SELECT $5::varchar AS source, $6::jsonb AS run_info) s
                ON CONFLICT (classification_id, jurisdiction_requirement_id) DO UPDATE SET
                    codified_at = NOW(), source = EXCLUDED.source, run_info = EXCLUDED.run_info
                RETURNING (xmax = 0) AS inserted
                """,
                [link["classification_id"] for link in links],
                [link["jurisdiction_requirement_id"] for link in links],
                [link["regulation_key"] for link in links],
                [link["jurisdiction_id"] for link in links],
                source, run_info_json,
            )
            inserted = sum(1 for r in result if r["inserted"])
            updated = len(result) - inserted

        if stamps:
            req_ids = list(stamps.keys())
            citations = [stamps[r]["statute_citation"] for r in req_ids]
            item_ids = [stamps[r]["citation_item_id"] for r in req_ids]
            verified_json = [
                json.dumps({"verified_citations": stamps[r]["verified_citations"]})
                for r in req_ids
            ]
            await conn.execute(
                """
                UPDATE jurisdiction_requirements AS jr
                SET statute_citation = t.citation,
                    citation_item_id = t.item_id,
                    citation_verified_at = NOW(),
                    metadata = COALESCE(jr.metadata, '{}'::jsonb) || t.verified::jsonb
                FROM unnest($1::uuid[], $2::text[], $3::uuid[], $4::jsonb[])
                    AS t(req_id, citation, item_id, verified)
                WHERE jr.id = t.req_id
                """,
                req_ids, citations, item_ids, verified_json,
            )
            citations_stamped = len(stamps)
            overwrote_manual = sum(
                1 for rid in stamps
                if rid in manual_before
                and stamps[rid]["statute_citation"] != prior_citation_by_id.get(rid)
            )

        # Self-correct: a row that was registry-verified but no longer has a
        # supporting citation this run (classification removed, or the jurisdiction
        # guard now rejects a cross-state link written by an older reconcile) is
        # downgraded verified→unverified. Only the verified markers + the
        # verified_citations breadcrumb are cleared; the statute_citation TEXT is
        # kept (mirrors the PATCH liveness reset) so the pointer back to the
        # authority survives transient registry churn instead of being erased.
        # Only touches registry stamps (verified_at set) — hand-curated citations
        # (verified_at NULL) are untouched.
        cleared = await conn.fetchval(
            """
            WITH c AS (
                UPDATE jurisdiction_requirements AS jr
                SET citation_item_id = NULL,
                    citation_verified_at = NULL,
                    metadata = COALESCE(jr.metadata, '{}'::jsonb) - 'verified_citations'
                WHERE jr.id = ANY($1::uuid[])
                  AND jr.citation_verified_at IS NOT NULL
                  AND NOT (jr.id = ANY($2::uuid[]))
                RETURNING 1
            ) SELECT COUNT(*) FROM c
            """,
            [r["id"] for r in requirement_rows], stamped_ids,
        )

    matched_classification_ids = {link["classification_id"] for link in links}
    unmatched_keys = sorted({
        c["regulation_key"] for c in classifications
        if c["id"] not in matched_classification_ids
    })

    return {
        "classifications_checked": len(classifications),
        "matched": len(links),
        "inserted": inserted,
        "updated": updated,
        "unmatched_keys": unmatched_keys,
        "citations_stamped": citations_stamped,
        "overwrote_manual": overwrote_manual,
        "citations_cleared": int(cleared or 0),
    }
