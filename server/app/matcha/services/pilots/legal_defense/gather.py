"""Evidence gathering — jurisdiction resolution, the source registry, and
the corpus assembler ``gather_evidence``."""

import logging

from ._shared import _PER_SOURCE_CAP
from .law import _gather_case_law, _gather_law_cached
from .sources import (
    _src_accommodations,
    _src_agency_charges,
    _src_biometric_consent,
    _src_compliance,
    _src_compliance_alerts,
    _src_compliance_remediation,
    _src_discipline,
    _src_er_cases,
    _src_hiring_ai_audits,
    _src_incidents,
    _src_leave,
    _src_pay_equity,
    _src_pay_transparency,
    _src_policy_ack,
    _src_post_term_claims,
    _src_pre_termination,
    _src_separations,
    _src_training,
)
from .theory import _BROAD, resolve_matter_theory

logger = logging.getLogger(__name__)


async def resolve_matter_jurisdiction(conn, matter: dict) -> dict | None:
    """Resolve a matter's governing jurisdiction chain (ordered narrowest →
    broadest, e.g. state then federal) from its location or state override.
    Returns None when neither is set — callers treat that as "no jurisdiction
    grounding available", not an error.

    Precedence: the location governs when set — both the chain AND the state
    come from it, and any ``jurisdiction_state`` override is ignored (the
    same rule ``legal_research.run_research`` applies, so the governing-law
    chain and the case-law search can never silently diverge).

    Deliberately NOT ``compliance_service.resolve_jurisdiction_stack`` — that
    CTE drags every requirement row along; this only needs the chain."""
    loc = None
    jid = None
    state = (matter.get("jurisdiction_state") or "").upper() or None
    if matter.get("location_id"):
        loc = await conn.fetchrow(
            "SELECT jurisdiction_id, name, state FROM business_locations "
            "WHERE id = $1 AND company_id = $2",
            matter["location_id"], matter["company_id"],
        )
        if loc:
            jid = loc["jurisdiction_id"]
            state = ((loc["state"] or "").upper() or None) or state
    if jid is None and state:
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE state = $1 AND level = 'state' "
            "AND country_code = 'US' LIMIT 1",
            state,
        )
        jid = row["id"] if row else None
    if jid is None:
        return None
    chain = await conn.fetch(
        """WITH RECURSIVE chain AS (
             SELECT id, parent_id, level, display_name, 0 AS depth
             FROM jurisdictions WHERE id = $1
             UNION ALL
             SELECT j.id, j.parent_id, j.level, j.display_name, c.depth + 1
             FROM jurisdictions j JOIN chain c ON j.id = c.parent_id
             WHERE c.depth < 6)
           SELECT id, level, display_name FROM chain ORDER BY depth""",
        jid,
    )
    return {
        "jurisdiction_id": jid,
        "chain": [dict(r) for r in chain],
        "state": state,
        "location_name": loc["name"] if loc else None,
    }
# (key, label, query-fn, enabled(features)-predicate)
_SOURCES = [
    ("incidents", "Safety incidents (IR / OSHA)", _src_incidents,
     lambda f: bool(f.get("incidents"))),
    ("er_cases", "Employee-relations cases", _src_er_cases,
     lambda f: True),  # er_copilot has no feature gate in defaults
    ("compliance", "Compliance requirements tracked", _src_compliance,
     lambda f: bool(f.get("compliance") or f.get("compliance_lite"))),
    ("compliance_alerts", "Compliance monitoring alerts", _src_compliance_alerts,
     lambda f: bool(f.get("compliance") or f.get("compliance_lite"))),
    ("compliance_remediation", "Compliance issues detected & remediated", _src_compliance_remediation,
     lambda f: bool(f.get("compliance") or f.get("compliance_lite"))),
    ("discipline", "Progressive discipline", _src_discipline,
     lambda f: bool(f.get("discipline"))),
    ("training", "Training completions", _src_training,
     lambda f: bool(f.get("training"))),
    ("policy_ack", "Policy / handbook acknowledgments", _src_policy_ack,
     lambda f: bool(f.get("handbooks", True))),
    ("accommodations", "Accommodation cases", _src_accommodations,
     lambda f: bool(f.get("accommodations", True))),
    # Employee-linked HR history. `employees` is the honest gate for the four
    # that hang off an employee row (pre_termination's own mount gate is the
    # same); separations rides its own product flag.
    ("leave", "Leave of absence (FMLA / PFML / medical)", _src_leave,
     lambda f: bool(f.get("employees"))),
    ("agency_charges", "Agency charges (EEOC / NLRB / OSHA / state)", _src_agency_charges,
     lambda f: bool(f.get("employees"))),
    ("pre_termination", "Pre-termination risk reviews", _src_pre_termination,
     lambda f: bool(f.get("employees"))),
    ("separations", "Separation agreements", _src_separations,
     lambda f: bool(f.get("separation_agreements"))),
    ("post_term_claims", "Post-termination claims", _src_post_term_claims,
     lambda f: bool(f.get("employees"))),
    # Employment-practices registers the company keeps about itself. All four ride
    # the one `workforce_compliance` flag that gates the trackers that write them —
    # see the block comment above their queries for why none is date- or
    # subject-filtered.
    ("pay_equity", "Pay-equity studies (register)", _src_pay_equity,
     lambda f: bool(f.get("workforce_compliance"))),
    ("hiring_ai_audits", "AI hiring-tool bias audits (register)", _src_hiring_ai_audits,
     lambda f: bool(f.get("workforce_compliance"))),
    ("pay_transparency", "Pay-transparency posting status (by state)", _src_pay_transparency,
     lambda f: bool(f.get("workforce_compliance"))),
    ("biometric_consent", "Biometric / BIPA consent inventory", _src_biometric_consent,
     lambda f: bool(f.get("workforce_compliance"))),
]


async def gather_evidence(conn, company_id, start, end, features: dict, matter: dict | None = None,
                          apply_theory: bool = True) -> dict:
    """Assemble the in-scope evidence corpus across every enabled subsystem.

    Each source is isolated: a failure (missing column, transient error) degrades
    that source to "unavailable" and is noted — it never aborts the whole gather.
    Returns ``{sources, index, notes, legal_context, theory}`` where ``index`` is
    a flat cid→record map used for citation validation and the PDF evidence index.

    ``matter`` is optional (keyword, default None) so existing callers stay
    source-compatible; when given, (a) location-capable record sources are
    scoped to the matter's location/state (er_cases + policy acks stay
    company-wide — no location link exists for them), (b) every subject-bearing
    source is filtered to the matter's theory (see ``resolve_matter_theory``),
    and (c) jurisdiction-grounded law/legislation/case-law sources are added.

    ``apply_theory=False`` keeps (a) and (c) but skips (b). The packet path uses
    it: ``build_defense_packet`` promises the appendix and ZIP carry every
    incident / ER / discipline record in scope, cited or not, precisely so the
    exhibit can't be read as selective. Subject relevance is a chat and sidebar
    concern; an attorney deliverable that quietly omits a whole category of
    records is the thing that docstring exists to prevent.
    """
    features = features or {}
    sources: dict = {}
    notes: list[str] = []
    theory, topic = resolve_matter_theory(matter) if apply_theory else (None, _BROAD)

    # Resolve jurisdiction BEFORE the sources loop: the record queries scope on
    # the matter's location/state, not just the legal-landscape extras below.
    legal_context = None
    if matter:
        try:
            legal_context = await resolve_matter_jurisdiction(conn, matter)
        except Exception as e:  # noqa: BLE001
            logger.warning("legal_defense: jurisdiction resolve failed: %s", e)
            notes.append("Jurisdiction: unavailable")

    loc_id = (matter or {}).get("location_id")
    # legal_context["state"] already encodes location-over-state precedence;
    # fall back to the raw override so state scoping still applies when
    # resolution fails (unknown state / location without a jurisdiction row).
    scope_state = (legal_context or {}).get("state") or (matter or {}).get("jurisdiction_state")

    # Sources this company doesn't run at all. Recorded so nothing downstream —
    # the model especially — can read their absence as "no such records exist".
    disabled = [label for _k, label, _fn, enabled in _SOURCES if not enabled(features)]

    for key, label, fn, enabled in _SOURCES:
        if not enabled(features):
            continue
        try:
            recs = await fn(conn, company_id, start, end, loc_id, scope_state, topic)
        except Exception as e:  # noqa: BLE001 — isolation is the point
            logger.warning("legal_defense: source %s unavailable: %s", key, e)
            notes.append(f"{label}: unavailable")
            continue
        if not recs:
            continue
        if len(recs) > _PER_SOURCE_CAP:
            notes.append(f"{label}: showing {_PER_SOURCE_CAP} most recent of {len(recs)}")
            recs = recs[:_PER_SOURCE_CAP]
        sources[key] = {"label": label, "records": recs}

    if loc_id or scope_state:
        notes.append(f"Evidence scoped to {(legal_context or {}).get('location_name') or scope_state}.")

    # Notes are rendered verbatim into the attorney-facing packet PDF's "Scope
    # notes" section, so they state facts about the compilation and nothing else
    # — never app-navigation instructions counsel can't act on. The escape-hatch
    # copy ("widen the subject") lives in the UI, where the control does.
    if theory:
        notes.append(
            f"Evidence filtered to this matter's {topic.label} subject; "
            f"records on unrelated subjects are excluded."
        )
    if start or end:
        notes.append(f"Evidence window: {start or 'earliest record'} to {end or 'present'}.")
    if disabled:
        # "not included", never "don't exist" — a feature can be switched off
        # after records were created, so absence here proves nothing.
        notes.append("Not included (subsystem not enabled for this company): "
                     + ", ".join(disabled) + ".")

    if matter:
        if legal_context:
            try:
                law_src, bill_src = await _gather_law_cached(conn, matter, legal_context, topic)
                if law_src and law_src["records"]:
                    sources["law"] = law_src
                if bill_src and bill_src["records"]:
                    sources["legislation"] = bill_src
            except Exception as e:  # noqa: BLE001
                logger.warning("legal_defense: law source unavailable: %s", e)
                notes.append("Governing requirements (jurisdiction): unavailable")
        try:
            case_src = await _gather_case_law(
                conn, matter.get("id"), (legal_context or {}).get("state"), theory)
            if case_src and case_src["records"]:
                sources["case_law"] = case_src
        except Exception as e:  # noqa: BLE001
            logger.warning("legal_defense: case-law source unavailable: %s", e)
            notes.append("Case law (external research): unavailable")

    index: dict = {}
    for key, s in sources.items():
        for r in s["records"]:
            index[r["cid"]] = {**r, "source": key, "source_label": s["label"]}

    return {"sources": sources, "index": index, "notes": notes,
            "legal_context": legal_context,
            # Carried so downstream callers can tell "feature off" from "no
            # records" — the sources dict alone conflates them (see intake_gaps).
            "features": features,
            "theory": {
                "slug": theory,
                "label": topic.label,
                # Derived subjects are a guess the user can correct; stored ones
                # are their decision. The UI says so, and shouldn't guess which.
                "overridden": bool((matter or {}).get("subject_theory")),
            } if theory else None}
