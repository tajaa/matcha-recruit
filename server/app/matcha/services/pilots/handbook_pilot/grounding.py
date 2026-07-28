"""DB reads that gather the tenant's own material before a corpus is built:
handbook profile + locations + existing sections/policies, the latest completed
audit's open gaps, the latest freshness findings per handbook, and the
precedence-resolved compliance floor.
"""
import json
import logging

from ._config import _MAX_EXISTING_POLICIES, _MAX_EXISTING_SECTIONS, _MAX_FRESHNESS_FINDINGS

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Grounding — fetch the raw records the corpus is built from. DB-touching.
# --------------------------------------------------------------------------- #

async def gather_grounding(conn, company_id, session: dict) -> dict:
    """Fetch the raw grounding material for a session: handbook profile,
    applicable jurisdiction requirements, existing handbook sections, existing
    policies. Best-effort at every level — a dead source degrades to empty and
    the chat still grounds on whatever else is available."""
    from app.core.services import handbook_service as hb

    # Always re-derive scopes from the live employee roster so a company that
    # expands into a new state grounds on that state's requirements immediately
    # (the session snapshot, seeded at create time, is only a fallback when
    # derivation fails or the roster is empty).
    snapshot = session.get("scopes") or []
    if isinstance(snapshot, str):
        import json
        try:
            snapshot = json.loads(snapshot)
        except Exception:
            snapshot = []
    try:
        derived = await hb.derive_handbook_scopes_from_employees(conn, str(company_id))
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: scope derivation failed for %s", company_id)
        derived = []
    scopes = derived or snapshot

    profile = None
    try:
        profile = await conn.fetchrow(
            "SELECT * FROM company_handbook_profiles WHERE company_id = $1", company_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: profile fetch failed for %s", company_id)

    requirements: dict = {}
    if scopes:
        try:
            requirements = await hb._fetch_state_requirements(conn, scopes)
        except Exception:  # noqa: BLE001
            logger.warning("handbook_pilot: requirement fetch failed for %s", company_id)
            requirements = {}

    sections: list = []
    try:
        sections = await conn.fetch(
            """
            SELECT hs.id, hs.title, hs.section_key, hs.section_type, hs.content,
                   h.title AS handbook_title
            FROM handbook_sections hs
            JOIN handbook_versions hv ON hv.id = hs.handbook_version_id
            JOIN handbooks h ON h.id = hv.handbook_id
            WHERE h.company_id = $1
              AND h.status IN ('active', 'draft')
              AND hv.version_number = h.active_version
            ORDER BY h.status = 'active' DESC, hs.section_order
            LIMIT $2
            """,
            company_id, _MAX_EXISTING_SECTIONS,
        )
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: existing-section fetch failed for %s", company_id)

    policies: list = []
    try:
        policies = await conn.fetch(
            """
            SELECT id, title, category, status, description, content
            FROM policies
            WHERE company_id = $1 AND status IN ('active', 'draft')
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            company_id, _MAX_EXISTING_POLICIES,
        )
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: existing-policy fetch failed for %s", company_id)

    audit = await _fetch_audit_gaps(conn, company_id)
    freshness = await _fetch_freshness_findings(conn, company_id)

    return {
        "scopes": scopes,
        "profile": dict(profile) if profile else None,
        "audit": audit,
        "freshness": freshness,
        "requirements": requirements,
        "sections": [dict(r) for r in sections],
        "policies": [dict(r) for r in policies],
        "industry": session.get("industry"),
        # Filled by `attach_compliance_floor` AFTER the caller releases `conn` —
        # see that function for why it cannot be fetched here.
        "reasoning_chains": [],
    }


async def _fetch_audit_gaps(conn, company_id) -> dict:
    """The company's latest completed handbook **audit** — the graded gap list
    from `handbook_audit_service`.

    Gated on the company's own `handbook_audit` flag. Handbook Pilot's tiers (X
    + Pro) carry that flag today, so the check is belt-and-braces rather than a
    live gate — but `handbook_audit_reports` is also written by the PUBLIC
    lead-gen analyzer, which any signed-in user can run, and grounding a paid
    drafting tool on a report the company can't open in-app would cite findings
    it has no way to inspect or dispute.

    Scoped through `clients` (user → company): the table is keyed on the user or
    email that uploaded the PDF, not on a company, so there is no company_id to
    filter. Company-wide rather than per-admin on purpose — the finding is about
    the company's handbook, and a second admin drafting against it should not be
    told the gaps don't exist because a colleague ran the audit.

    Best-effort: any failure degrades to ``{}`` and the corpus simply carries no
    audit records."""
    try:
        flags = await conn.fetchrow(
            "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id)
        if flags:
            from app.core.feature_flags import merge_company_features
            if not merge_company_features(
                    flags["enabled_features"], flags["signup_source"]).get("handbook_audit"):
                return {}
        row = await conn.fetchrow(
            """
            SELECT r.id, r.states, r.industry, r.gaps_jsonb, r.gap_counts,
                   r.created_at, r.completed_at
            FROM handbook_audit_reports r
            JOIN clients cl ON cl.user_id = r.user_id
            WHERE cl.company_id = $1 AND r.status = 'ready'
            ORDER BY r.completed_at DESC NULLS LAST, r.created_at DESC
            LIMIT 1
            """,
            company_id,
        )
    except Exception:  # noqa: BLE001 — a missing audit is a note, never an error
        logger.warning("handbook_pilot: audit fetch failed for %s", company_id)
        return {}
    if not row:
        return {}
    gaps = row["gaps_jsonb"]
    if isinstance(gaps, str):
        try:
            gaps = json.loads(gaps)
        except (json.JSONDecodeError, TypeError):
            gaps = []
    return {
        "report_id": str(row["id"]),
        "states": list(row["states"] or []),
        "industry": row["industry"],
        "completed_at": row["completed_at"] or row["created_at"],
        "gaps": [g for g in (gaps or []) if isinstance(g, dict)],
    }


async def _fetch_freshness_findings(conn, company_id) -> list[dict]:
    """Findings from the LATEST completed freshness check of each of the
    company's handbooks — "the law moved under section X since this was written".

    One check per handbook, not the company's latest check overall: a company
    with a US and a CA handbook would otherwise ground on whichever was swept
    most recently and silently carry nothing for the other.

    No feature gate. The manual `POST /handbooks/{id}/freshness-check` ships with
    `handbooks`, which every Handbook Pilot tenant has; `handbook_watch` gates
    only the SCHEDULED sweep that also writes these rows. Gating the read on
    `handbook_watch` would hide the company's own manual findings from it."""
    try:
        rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT DISTINCT ON (handbook_id) id, handbook_id, created_at
                FROM handbook_freshness_checks
                WHERE company_id = $1 AND status = 'completed'
                ORDER BY handbook_id, created_at DESC
            )
            SELECT f.id, f.handbook_id, f.section_key, f.finding_type, f.summary,
                   f.source_url, f.effective_date, f.age_days, f.change_request_id,
                   l.created_at AS checked_at, h.title AS handbook_title
            FROM latest l
            JOIN handbook_freshness_findings f ON f.freshness_check_id = l.id
            LEFT JOIN handbooks h ON h.id = f.handbook_id
            ORDER BY l.created_at DESC, f.created_at
            LIMIT $2
            """,
            company_id, _MAX_FRESHNESS_FINDINGS + 1,
        )
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: freshness fetch failed for %s", company_id)
        return []
    return [dict(r) for r in rows]


async def attach_compliance_floor(grounding: dict, company_id) -> dict:
    """Add the precedence-resolved compliance floor to a `gather_grounding`
    result: the GOVERNING requirement per category (federal → state → local),
    which is what a drafting tool should write against — `requirements` is the
    flat overlapping list.

    **Call this OUTSIDE the caller's `async with get_connection()` block.**
    `build_compliance_context` opens its own pooled connection, so invoking it
    while the route still holds one nests two acquisitions out of a pool of ten;
    enough concurrent cold-cache requests then hold every slot while waiting for
    a second and none can finish. HR Pilot solved this the same way and says so
    at `matcha_work_mode_contexts._build_hr_pilot_bundle_uncached`.

    No cache layer of its own: `build_compliance_context` is already Redis-cached
    behind a per-key build lock (120s, `mw:compliance_ctx:{company_id}`) and the
    chains survive the round-trip, so the expensive resolution runs at most once
    per company per window no matter which pilot asks. Degrades to empty, like
    every other source in `gather_grounding`."""
    chains: list = []
    try:
        from app.matcha.services.matcha_work import matcha_work_node
        result = await matcha_work_node.build_compliance_context(company_id)
        chains = list(getattr(result, "reasoning_chains", None) or [])
    except Exception:  # noqa: BLE001 — a missing floor is a note, never an error
        logger.warning("handbook_pilot: compliance floor fetch failed for %s", company_id)
    grounding = grounding or {}
    grounding["reasoning_chains"] = chains
    return grounding
