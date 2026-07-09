"""Limit-adequacy + contract review (gap-analysis #6/#28).

The WTW report names benchmarking + **contractual-limit review** an "essential
tool." This turns two owned inputs into a concrete, money-relevant deliverable:

  - what the company actually CARRIES (``company_coverage_lines``), and
  - what its CONTRACTS require (``company_contracts.requirements`` — extracted by
    ``contract_parser`` or keyed by hand),

…diffed per casualty line. A contract-required limit the company doesn't meet is
a HARD, grounded gap ("you carry $1M GL but Acme's MSA requires $2M"). Where no
contract speaks, a coarse industry/size/venue **heuristic baseline** flags lines
that look light — clearly labelled directional, never a precise peer benchmark
(we don't have peer-limit data, same gap as licensed NCCI rates).

Pure ``analyze`` (unit-tested) + a DB ``build_review`` wrapper (never raises) +
a deterministic PDF. Mirrors controls_evidence / exclusion_gap structure.
"""

import asyncio
import html
import logging
from typing import Optional
from uuid import UUID

from app.core.services.pdf import safe_url_fetcher

logger = logging.getLogger(__name__)

# Brokers review insurance and risk-transfer provisions — never the whole
# agreement. Every rendered surface carries this; `risk_transfer` re-exports it.
DISCLAIMER = (
    "Review limited to insurance and risk-transfer provisions. Not legal advice — "
    "have counsel review the full agreement."
)

# Casualty lines we model. ``endorsements`` = whether contract endorsement
# requirements (AI / WOS / P&NC) are meaningful for the line.
COVERAGE_LINES = [
    {"key": "gl", "label": "General Liability", "endorsements": True},
    {"key": "auto", "label": "Commercial Auto", "endorsements": True},
    {"key": "umbrella", "label": "Umbrella / Excess", "endorsements": False},
    {"key": "wc", "label": "Workers' Comp / Employers Liability", "endorsements": True},
    {"key": "epl", "label": "Employment Practices Liability", "endorsements": False},
    {"key": "professional", "label": "Professional Liability (E&O)", "endorsements": False},
    {"key": "cyber", "label": "Cyber Liability", "endorsements": False},
    {"key": "property", "label": "Commercial Property", "endorsements": False},
]
LINE_KEYS = {c["key"] for c in COVERAGE_LINES}
_LINE_LABEL = {c["key"]: c["label"] for c in COVERAGE_LINES}
_LINE_ENDORSE = {c["key"]: c["endorsements"] for c in COVERAGE_LINES}

# Endorsement booleans carried on company_coverage_lines + extractable from a
# contract requirement.
ENDORSEMENTS = [
    {"key": "additional_insured", "label": "Additional insured"},
    {"key": "waiver_of_subrogation", "label": "Waiver of subrogation"},
    {"key": "primary_noncontributory", "label": "Primary & non-contributory"},
]
_ENDORSE_LABEL = {e["key"]: e["label"] for e in ENDORSEMENTS}

# Free-text line names → our keys (used when a contract is parsed/keyed).
LINE_ALIASES = {
    "general liability": "gl", "cgl": "gl", "commercial general liability": "gl", "gl": "gl",
    "auto": "auto", "automobile": "auto", "commercial auto": "auto", "auto liability": "auto",
    "business auto": "auto", "hired and non-owned auto": "auto",
    "umbrella": "umbrella", "excess": "umbrella", "umbrella/excess": "umbrella",
    "excess liability": "umbrella", "umbrella liability": "umbrella",
    "workers comp": "wc", "workers compensation": "wc", "workers' compensation": "wc",
    "employers liability": "wc", "wc": "wc", "el": "wc",
    "epl": "epl", "employment practices": "epl", "employment practices liability": "epl",
    "professional": "professional", "professional liability": "professional",
    "errors and omissions": "professional", "e&o": "professional", "eo": "professional",
    "cyber": "cyber", "cyber liability": "cyber", "data breach": "cyber",
    "property": "property", "commercial property": "property", "building": "property",
    "buildings and contents": "property", "property damage": "property",
    "first party property": "property", "real property": "property",
}


def normalize_line(raw: Optional[str]) -> Optional[str]:
    """Map a free-text coverage-line name to one of our keys (else None)."""
    if not raw:
        return None
    k = str(raw).strip().lower()
    if k in LINE_KEYS:
        return k
    return LINE_ALIASES.get(k)


# --- heuristic baseline (directional, NOT a peer benchmark) -----------------

def _headcount_band(headcount: Optional[int]) -> str:
    n = headcount or 0
    if n >= 250:
        return "large"
    if n >= 50:
        return "mid"
    return "small"


def recommend_baseline(line: str, headcount: Optional[int], venue_tier: Optional[str]) -> Optional[dict]:
    """Coarse directional floor for a line by company size + venue severity.

    Deliberately rough — a starting point a broker refines, not a quote. Returns
    {per_occurrence, aggregate, basis} or None for lines we don't floor.
    """
    band = _headcount_band(headcount)
    severe_venue = venue_tier in ("severe", "high")
    M = 1_000_000

    if line == "gl":
        agg = 4 * M if band == "large" else 2 * M
        return {"per_occurrence": M, "aggregate": agg,
                "basis": f"$1M/occ, ${agg // M}M agg baseline for a {band} employer"}
    if line == "auto":
        return {"per_occurrence": M, "aggregate": None,
                "basis": "$1M combined-single-limit baseline (raise with owned fleet)"}
    if line == "umbrella":
        base = {"small": 1, "mid": 5, "large": 10}[band]
        if severe_venue:
            base += 5
        return {"per_occurrence": base * M, "aggregate": base * M,
                "basis": f"${base}M umbrella for a {band} employer"
                         + (" in a high-severity venue" if severe_venue else "")}
    if line == "wc":
        return {"per_occurrence": M, "aggregate": None,
                "basis": "$1M employers-liability baseline atop statutory WC"}
    if line == "epl":
        po = {"small": 1, "mid": 2, "large": 3}[band] * M
        return {"per_occurrence": po, "aggregate": po,
                "basis": f"${po // M}M EPL baseline — exposure scales with headcount"}
    if line == "cyber":
        return {"per_occurrence": M, "aggregate": M,
                "basis": "$1M cyber baseline (raise with PII / payment volume)"}
    # professional: too industry-specific to floor generically
    return None


# --- pure adequacy analysis -------------------------------------------------

def _max_required(contracts: list[dict], line: str) -> tuple[Optional[float], Optional[float], list[dict], set]:
    """Across all contracts, the highest per-occ + aggregate required for ``line``,
    the contracts that drive it, and the union of required endorsements."""
    po = agg = None
    sources: list[dict] = []
    endorsements: set = set()
    for c in contracts:
        for req in c.get("requirements") or []:
            if normalize_line(req.get("line")) != line:
                continue
            rpo = _num(req.get("per_occurrence"))
            ragg = _num(req.get("aggregate"))
            if rpo is not None:
                po = rpo if po is None else max(po, rpo)
            if ragg is not None:
                agg = ragg if agg is None else max(agg, ragg)
            for e in ENDORSEMENTS:
                if req.get(e["key"]):
                    endorsements.add(e["key"])
            sources.append({"contract": c.get("name"), "counterparty": c.get("counterparty"),
                            "per_occurrence": rpo, "aggregate": ragg})
    return po, agg, sources, endorsements


def _num(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def analyze(carried: list[dict], contracts: list[dict], *, headcount: Optional[int],
            venue_tier: Optional[str], industry: Optional[str] = None) -> dict:
    """Diff carried limits vs contract requirements + heuristic baseline. Pure.

    Per line status:
      - no_coverage   — a contract requires the line, nothing carried (HARD)
      - shortfall     — carried below a contract-required limit (HARD)
      - directional_low — no contract, carried below the heuristic baseline (soft)
      - not_carried   — no contract + nothing carried (informational)
      - ok            — meets contract requirement (or baseline) where present
    """
    carried_by = {normalize_line(c.get("line")) or c.get("line"): c for c in carried}
    lines_out: list[dict] = []
    contract_shortfalls = baseline_lows = 0

    for spec in COVERAGE_LINES:
        line = spec["key"]
        have = carried_by.get(line)
        req_po, req_agg, sources, req_endorse = _max_required(contracts, line)
        baseline = recommend_baseline(line, headcount, venue_tier)

        have_po = _num(have.get("per_occurrence")) if have else None
        have_agg = _num(have.get("aggregate")) if have else None

        status = "ok"
        gap = None
        if req_po is not None or req_agg is not None:
            if not have:
                status = "no_coverage"
                gap = f"Contract requires {_money(req_po or req_agg)} {_LINE_LABEL[line]} — none on file"
                contract_shortfalls += 1
            else:
                # A RECORDED limit below the requirement is a hard shortfall. A
                # limit the carried line simply doesn't record (None) is NOT proof
                # of a $0 limit — so don't treat a missing value as "carry —".
                po_short = req_po is not None and have_po is not None and have_po < req_po
                agg_short = req_agg is not None and have_agg is not None and have_agg < req_agg
                if po_short or agg_short:
                    status = "shortfall"
                    need = _money(req_po) if po_short else _money(req_agg)
                    has = _money(have_po) if po_short else _money(have_agg)
                    gap = f"Carry {has}, contract requires {need}"
                    contract_shortfalls += 1
                elif req_po is not None and have_po is None:
                    # primary (per-occ) limit required but not on file — a real gap to
                    # close, but phrased as "not recorded" rather than implying $0.
                    status = "shortfall"
                    gap = f"Contract requires {_money(req_po)} per-occurrence — none recorded on the carried line"
                    contract_shortfalls += 1
                elif req_agg is not None and have_agg is None:
                    # only the secondary aggregate is unrecorded (per-occ satisfies the
                    # contract): a data-completeness nudge, NOT a hard shortfall. Recording
                    # only per-occ must not false-flag every aggregate-naming contract line.
                    gap = f"Aggregate not on file — confirm it meets {_money(req_agg)}"
        elif not have:
            status = "not_carried"
        elif baseline and have_po is not None and have_po < baseline["per_occurrence"]:
            status = "directional_low"
            gap = f"Carry {_money(have_po)} — typical baseline ~{_money(baseline['per_occurrence'])}"
            baseline_lows += 1

        # endorsement gaps: required by a contract, not flagged on the carried line
        endorse_gaps = []
        if _LINE_ENDORSE.get(line) and req_endorse:
            for ek in req_endorse:
                if not (have and have.get(ek)):
                    endorse_gaps.append({"key": ek, "label": _ENDORSE_LABEL[ek]})

        lines_out.append({
            "key": line, "label": spec["label"],
            "carried": {
                "per_occurrence": have_po, "aggregate": have_agg,
                "retention": _num(have.get("retention")) if have else None,
                "carrier": have.get("carrier") if have else None,
                "expiry_date": str(have["expiry_date"]) if have and have.get("expiry_date") else None,
                "additional_insured": bool(have.get("additional_insured")) if have else False,
                "waiver_of_subrogation": bool(have.get("waiver_of_subrogation")) if have else False,
                "primary_noncontributory": bool(have.get("primary_noncontributory")) if have else False,
            } if have else None,
            "contract_required": {"per_occurrence": req_po, "aggregate": req_agg} if (req_po or req_agg) else None,
            "contract_sources": sources,
            "baseline": baseline,
            "status": status,
            "gap": gap,
            "endorsement_gaps": endorse_gaps,
        })

    summary = {
        "contract_shortfalls": contract_shortfalls,
        "baseline_lows": baseline_lows,
        "lines_carried": sum(1 for l in lines_out if l["carried"]),
        "contracts": len(contracts),
        "endorsement_gaps": sum(len(l["endorsement_gaps"]) for l in lines_out),
    }
    return {"lines": lines_out, "summary": summary,
            "contracts": [{"id": c.get("id"), "name": c.get("name"),
                           "counterparty": c.get("counterparty"), "status": c.get("status"),
                           "ai_available": c.get("ai_available"),
                           "contract_type": c.get("contract_type"),
                           "governing_state": c.get("governing_state"),
                           "project_state": c.get("project_state"),
                           "risk_transfer": c.get("risk_transfer"),
                           "confirmed_at": c.get("confirmed_at"),
                           "has_source": bool(c.get("storage_path")),
                           "requirements": c.get("requirements") or []} for c in contracts]}


def _money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    v = float(v)
    if v >= 1_000_000:
        n = v / 1_000_000
        return f"${n:.0f}M" if n == int(n) else f"${n:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


# --- DB wrapper (never raises) ---------------------------------------------

async def build_review(conn, company_id: UUID, *, venue: dict | None = None) -> dict:
    """Fetch carried lines + contracts + company profile + venue tier → analyze.

    ``venue`` may be a precomputed ``venue_severity.company_venue_exposure``
    result (the broker submission path already has one). Never raises — degrades
    to an empty review.
    """
    company_name = "Client"
    industry = None
    headcount = None
    carried: list[dict] = []
    contracts: list[dict] = []
    try:
        company = await conn.fetchrow(
            "SELECT name, industry FROM companies WHERE id = $1", company_id
        )
        if company:
            company_name = company["name"]
            industry = company["industry"]
        prof = await conn.fetchrow(
            "SELECT headcount FROM company_handbook_profiles WHERE company_id = $1", company_id
        )
        headcount = prof["headcount"] if prof else None
        carried = [dict(r) for r in await conn.fetch(
            """SELECT line, carrier, per_occurrence, aggregate, retention,
                      additional_insured, waiver_of_subrogation, primary_noncontributory,
                      effective_date, expiry_date, note
               FROM company_coverage_lines WHERE company_id = $1 ORDER BY line""",
            company_id,
        )]
        contracts = [_contract_row(r) for r in await conn.fetch(
            """SELECT id, name, counterparty, status, requirements, ai_available,
                      contract_type, governing_state, project_state, risk_transfer,
                      confirmed_at, storage_path
               FROM company_contracts WHERE company_id = $1 ORDER BY created_at DESC""",
            company_id,
        )]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("limit_adequacy.build_review fetch failed: %s", exc)

    venue_tier = None
    try:
        if venue is None:
            from . import venue_severity
            venue = await venue_severity.company_venue_exposure(conn, company_id)
        venue_tier = (venue.get("summary") or {}).get("worst_tier") if venue else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("limit_adequacy: venue lookup failed: %s", exc)

    review = analyze(carried, contracts, headcount=headcount, venue_tier=venue_tier, industry=industry)

    # Indemnity verdict per contract. Lazy import — risk_transfer imports this
    # module for the line vocabulary, so a top-level import would cycle.
    try:
        from . import risk_transfer
        for c in review["contracts"]:
            c["indemnity"] = risk_transfer.assess_indemnity(
                c.get("risk_transfer"),
                governing_state=c.get("governing_state"),
                project_state=c.get("project_state"),
                contract_type=c.get("contract_type"),
            )
            c["provisional"] = not c.get("confirmed_at")
    except Exception as exc:  # pragma: no cover - defensive; verdicts are additive
        logger.warning("limit_adequacy: indemnity verdicts unavailable: %s", exc)

    review["company_id"] = str(company_id)
    review["company_name"] = company_name
    review["headcount"] = headcount
    review["industry"] = industry
    review["venue_tier"] = venue_tier
    review["disclaimer"] = DISCLAIMER
    return review


def _contract_row(r) -> dict:
    """Row → dict. The pool has no jsonb codec, so jsonb columns arrive as raw
    strings and must be decoded explicitly."""
    import json
    d = dict(r)
    d["id"] = str(d["id"])
    req = d.get("requirements")
    if isinstance(req, str):
        try:
            req = json.loads(req)
        except json.JSONDecodeError:
            req = []
    d["requirements"] = req if isinstance(req, list) else []
    if "risk_transfer" in d:
        rt = d["risk_transfer"]
        if isinstance(rt, str):
            try:
                rt = json.loads(rt)
            except json.JSONDecodeError:
                rt = None
        d["risk_transfer"] = rt if isinstance(rt, dict) else None
    return d


# --- deterministic PDF ------------------------------------------------------

def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


_STATUS_LABEL = {"no_coverage": "NO COVER", "shortfall": "SHORTFALL",
                 "directional_low": "LOW", "not_carried": "NOT CARRIED", "ok": "OK"}
_STATUS_CLASS = {"no_coverage": "bad", "shortfall": "bad", "directional_low": "warn",
                 "not_carried": "muted", "ok": "good"}


def _limit_rows_html(review: dict) -> str:
    rows = ""
    for l in review.get("lines") or []:
        c = l.get("carried") or {}
        req = l.get("contract_required") or {}
        base = l.get("baseline") or {}
        carried_s = _money(c.get("per_occurrence")) + (f" / {_money(c.get('aggregate'))}" if c.get("aggregate") else "")
        req_s = (_money(req.get("per_occurrence")) + (f" / {_money(req.get('aggregate'))}" if req.get("aggregate") else "")) if req else "—"
        base_s = _money(base.get("per_occurrence")) if base else "—"
        rows += (
            f"<tr><td>{_esc(l['label'])}</td>"
            f"<td class='r'>{carried_s if l.get('carried') else '—'}</td>"
            f"<td class='r'>{req_s}</td>"
            f"<td class='r'>{base_s}</td>"
            f"<td class='st {_STATUS_CLASS.get(l['status'], 'muted')}'>{_STATUS_LABEL.get(l['status'], l['status'].upper())}</td>"
            f"<td>{_esc(l.get('gap'))}</td></tr>"
        )
        eg = l.get("endorsement_gaps") or []
        if eg:
            rows += (f"<tr class='note'><td colspan='6'>Required endorsements to confirm: "
                     f"{_esc(', '.join(e['label'] for e in eg))}</td></tr>")
    return rows


_VERDICT_LABEL = {"likely_void_by_statute": "LIKELY VOID", "uninsurable_exposure": "UNINSURABLE",
                  "insurable": "INSURABLE", "review": "NEEDS REVIEW"}
_VERDICT_CLASS = {"likely_void_by_statute": "st bad", "uninsurable_exposure": "st bad",
                  "insurable": "st good", "review": "st muted"}


def risk_transfer_rows_html(review: dict, esc=None, verdict_class: dict | None = None) -> str:
    """Per-contract indemnity verdicts, as ``<tr>`` rows.

    Shared by this module's PDF and the broker submission packet. Both supply
    their own escaper and verdict→CSS map, because the two stylesheets name their
    status classes differently (``st bad`` here, ``lim-bad`` there)."""
    esc = esc or _esc
    cls = verdict_class or _VERDICT_CLASS
    rows = ""
    for c in review.get("contracts") or []:
        ind = c.get("indemnity") or {}
        rt = (c.get("risk_transfer") or {}).get("indemnity") or {}
        if not rt.get("present") and not c.get("contract_type"):
            continue
        form = str(rt.get("form") or "—").replace("_", " ")
        prov = " <em>(provisional)</em>" if c.get("provisional") else ""
        rows += (
            f"<tr><td>{esc(c.get('name'))}</td>"
            f"<td>{esc((c.get('contract_type') or '—').replace('_', ' '))}</td>"
            f"<td>{esc(c.get('project_state') or c.get('governing_state'))}</td>"
            f"<td>{esc(form)}</td>"
            f"<td class='{cls.get(ind.get('verdict'), cls.get('review', ''))}'>"
            f"{_VERDICT_LABEL.get(ind.get('verdict'), '—')}{prov}</td>"
            f"<td>{esc(ind.get('statute'))}</td></tr>"
        )
    return rows


def _risk_transfer_html(review: dict) -> str:
    rows = risk_transfer_rows_html(review)
    if not rows:
        return ""
    return (
        "<h2>Indemnification &amp; risk transfer</h2>"
        "<table><thead><tr><th>Contract</th><th>Type</th><th>State</th><th>Indemnity form</th>"
        "<th>Verdict</th><th>Statute</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _limits_html(company_name: str, review: dict) -> str:
    s = review.get("summary") or {}
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }}
      h1 {{ color:#1f8a5b; margin:0 0 2px; font-size:22px; }}
      .sub {{ color:#666; margin:0 0 16px; }}
      h2 {{ font-size:13px; border-bottom:2px solid #1f8a5b; padding-bottom:4px; margin:18px 0 8px; }}
      .grid {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
      .cell {{ border:1px solid #e5e7eb; border-radius:8px; padding:8px 12px; min-width:100px; }}
      .cell .l {{ font-size:8px; text-transform:uppercase; letter-spacing:.6px; color:#888; }}
      .cell .v {{ font-size:18px; font-weight:300; font-family:monospace; margin-top:3px; }}
      table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
      th {{ text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:4px 6px; }}
      td {{ padding:4px 6px; border-bottom:1px solid #f0f0f0; }}
      td.r {{ text-align:right; font-family:monospace; }}
      .st {{ font-size:8px; font-weight:700; }}
      .st.good{{color:#1f8a5b}} .st.warn{{color:#b8902f}} .st.bad{{color:#b23b3b}} .st.muted{{color:#999}}
      tr.note td {{ font-size:9px; color:#666; background:#fafafa; }}
      .foot {{ margin-top:24px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }}
    </style></head><body>
      <h1>Limit Adequacy &amp; Contract Review</h1>
      <p class="sub">{_esc(company_name)} — carried limits vs. contractual requirements</p>

      <h2>Summary</h2>
      <div class="grid">
        <div class="cell"><div class="l">Contract shortfalls</div><div class="v">{_esc(s.get('contract_shortfalls'))}</div></div>
        <div class="cell"><div class="l">Baseline-low</div><div class="v">{_esc(s.get('baseline_lows'))}</div></div>
        <div class="cell"><div class="l">Lines carried</div><div class="v">{_esc(s.get('lines_carried'))}</div></div>
        <div class="cell"><div class="l">Contracts</div><div class="v">{_esc(s.get('contracts'))}</div></div>
      </div>

      <h2>By coverage line</h2>
      <table><thead><tr><th>Line</th><th class="r">Carried (occ/agg)</th><th class="r">Contract req.</th>
        <th class="r">Baseline</th><th>Status</th><th>Gap</th></tr></thead>
        <tbody>{_limit_rows_html(review) or '<tr><td colspan="6">No coverage lines on file</td></tr>'}</tbody></table>

      {_risk_transfer_html(review)}

      <div class="foot">{_esc(DISCLAIMER)} Prepared by Matcha. Contract requirements were extracted from the client's
      uploaded contracts; baseline figures are directional size/venue heuristics, not peer benchmarks or a quote.
      Confirm endorsements and limits against the policy declarations. Present alongside the carrier loss run and
      insurance application.</div>
    </body></html>"""


async def render_review_pdf(company_name: str, review: dict) -> bytes:
    def _render() -> bytes:
        from weasyprint import HTML

        return HTML(string=_limits_html(company_name, review), url_fetcher=safe_url_fetcher).write_pdf()

    return await asyncio.to_thread(_render)
