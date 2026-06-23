"""Broker submission packet + AI coverage-gap analysis.

The "outward" layer (WTW p.4/p.11 thesis): turn a client's WC + EPL posture into
a carrier-ready underwriting submission PDF, plus an AI coverage-gap read. Works
for both on-platform (tenant) and off-platform clients — the caller builds a
common ``context`` dict; this module renders + analyzes it.

- PDF render is deterministic (no AI) so the leave-behind is always reliable —
  WeasyPrint off the event loop, SSRF-guarded (mirrors the stabilization kit).
- Coverage-gap is best-effort Gemini (never raises) — reuses the cached
  IRAnalyzer like broker_outreach.
"""

import asyncio
import html
import json
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None


def get_submission_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


# --- deterministic narrative (no AI, always present in the PDF) -------------

def _wc_narrative(ctx: dict) -> str:
    wc = ctx.get("wc") or {}
    if not wc or wc.get("trir") is None:
        return "No workers'-comp loss data on file for this period."
    cb = wc.get("claim_breakdown") or {}
    parts = [f"TRIR {wc['trir']} ({(wc.get('severity_band') or 'n/a').replace('_',' ')} vs the {ctx.get('industry') or 'industry'} benchmark)"]
    if cb.get("cumulative_trauma"):
        parts.append(f"{cb['cumulative_trauma']} cumulative-trauma claim(s)")
    if wc.get("post_termination_cases"):
        parts.append(f"{wc['post_termination_cases']} filed post-termination")
    rtw = wc.get("rtw") or {}
    if rtw.get("open"):
        parts.append(f"{rtw['open']} open lost-time claim(s)")
    if wc.get("current_emr") is not None:
        parts.append(f"experience mod {wc['current_emr']:.2f}")
    return "Primary WC profile: " + "; ".join(parts) + "."


def _epl_narrative(ctx: dict) -> str:
    epl = ctx.get("epl") or {}
    if not epl:
        return ""
    gaps = [f["label"] for f in (epl.get("factors") or []) if f.get("status") == "gap"][:3]
    base = f"EPL readiness {epl.get('score')}/100 ({(epl.get('band') or '').title()})."
    if gaps:
        base += " Open items: " + ", ".join(gaps) + "."
    return base


# --- coverage-gap (best-effort Gemini) -------------------------------------

_GAP_PROMPT = """You are an insurance broker's risk advisor. Given a client's profile and risk posture, identify likely coverage gaps and concrete recommendations. Be specific and concise; use the numbers given.

Ground every gap in the provided profile, posture, or the `exclusions` list in the context (a curated read of emerging exclusions this risk faces). Do NOT assert a gap for a coverage line that has no supporting data in the context — prefer the flagged exclusions over speculation.

Client profile + posture (JSON):
{context}

Current coverage the broker has on file (may be empty — if so, reason from the profile about typical coverage a company like this should carry):
{coverage}

Return ONLY valid JSON:
{{"summary": "<2-3 sentence headline read>",
  "gaps": [{{"line": "<coverage line, e.g. EPL / Cyber / Umbrella>", "concern": "<why, citing the client's numbers>", "suggestion": "<concrete e.g. increase EPL to $2M>"}}],
  "actions": ["<short loss-mitigation action the client should take before renewal>"]}}
Limit to the 4 most material gaps and 4 actions."""


async def generate_coverage_gap(*, context: dict, current_coverage: Optional[dict] = None) -> dict:
    """Best-effort AI coverage-gap. Never raises — returns {} payload on failure."""
    from app.core.services.rate_limiter import get_rate_limiter
    try:
        await get_rate_limiter().check_limit("ir_analysis", "broker_submission")
    except Exception:
        pass

    prompt = _GAP_PROMPT.format(
        context=json.dumps(context, default=str),
        coverage=json.dumps(current_coverage or {}, default=str),
    )
    analyzer = get_submission_analyzer()
    payload: dict = {}
    try:
        response = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=prompt),
            timeout=45,
        )
        raw = (getattr(response, "text", None) or "").strip()
        payload = analyzer._parse_json_response(raw) or {}
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning("Coverage-gap generation failed: %s", exc)
        payload = {}

    gaps = payload.get("gaps") if isinstance(payload.get("gaps"), list) else []
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    return {
        "summary": payload.get("summary") or "",
        "gaps": [g for g in gaps if isinstance(g, dict)][:4],
        "actions": [a for a in actions if isinstance(a, str)][:4],
        "model": analyzer.model,
        "available": bool(payload),
    }


# --- PDF render (deterministic) --------------------------------------------

def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


def _controls_section_html(register: Optional[dict]) -> str:
    """Optional Proof-of-Controls section appended to the submission PDF (tenant
    clients only — off-platform context has no controls register)."""
    controls = (register or {}).get("controls") or []
    if not controls:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(c.get('label'))}</td>"
        f"<td class='st {c.get('status')}'>{_esc((c.get('status') or '').upper())}</td>"
        f"<td>{_esc(c.get('metric'))}</td></tr>"
        for c in controls
    )
    s = register.get("summary") or {}
    return (
        f"<h2>Risk Controls — Proof of Controls "
        f"({_esc(s.get('strong'))} strong / {_esc(s.get('gap'))} gap)</h2>"
        f"<table><thead><tr><th>Control</th><th>Status</th><th>Evidence</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _readiness_section_html(readiness: Optional[dict]) -> str:
    """Optional pre-flight banner: how underwriter-ready the client's data is."""
    if not readiness:
        return ""
    summ = readiness.get("summary") or {}
    fixes = readiness.get("top_fixes") or []
    head = (
        f"<b>Submission readiness: {_esc(readiness.get('score'))}% "
        f"({_esc((readiness.get('band') or '').title())})</b> — "
        f"{_esc(summ.get('done'))}/{_esc(summ.get('total'))} underwriting inputs complete."
    )
    if fixes:
        lis = "".join(f"<li>{_esc(f)}</li>" for f in fixes)
        head += f"<div class='rfix'>Before marketing, complete:</div><ul>{lis}</ul>"
    return f"<div class='ready'>{head}</div>"


_VENUE_TONE = {"severe": "vt-severe", "high": "vt-high", "elevated": "vt-elev",
               "moderate": "vt-mod", "low": "vt-low", "unknown": "vt-unk"}


def _venue_section_html(venue: Optional[dict]) -> str:
    """Optional venue-exposure section: client locations vs nuclear-verdict /
    plaintiff-friendly venue severity. Exposure context, not a controllable score."""
    locs = (venue or {}).get("locations") or []
    if not locs:
        return ""
    s = venue.get("summary") or {}
    rows = "".join(
        f"<tr><td>{_esc(l.get('city') or '—')}</td><td>{_esc(l.get('county') or '—')}</td>"
        f"<td>{_esc(l.get('state'))}</td>"
        f"<td class='vt {_VENUE_TONE.get(l.get('tier'), 'vt-unk')}'>{_esc((l.get('tier') or '').upper())}</td></tr>"
        for l in locs
    )
    hi = s.get("severe_high_count") or 0
    headline = (f"{hi} of {s.get('total_locations')} location(s) in high-severity venues"
                if hi else f"{s.get('total_locations')} location(s) — no high-severity venues flagged")
    return (
        f"<h2>Venue Exposure — {_esc(headline)}</h2>"
        f"<table><thead><tr><th>Location</th><th>County</th><th>State</th><th>Venue severity</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


_EXCL_TONE = {"exposed": "ex-exposed", "monitor": "ex-monitor", "mitigated": "ex-mitigated"}


def _exclusions_section_html(ex: Optional[dict]) -> str:
    """Grounded emerging-exclusion exposure (PFAS, A&M, biometric, silent-cyber…)."""
    items = (ex or {}).get("exclusions") or []
    if not items:
        return ""
    s = ex.get("summary") or {}
    rows = "".join(
        f"<tr><td>{_esc(e.get('label'))}</td><td>{_esc(', '.join(e.get('lines') or []))}</td>"
        f"<td class='{_EXCL_TONE.get(e.get('status'), 'vt-unk')}'>{_esc((e.get('status') or '').upper())}</td>"
        f"<td>{_esc(e.get('mitigation'))}</td></tr>"
        for e in items
    )
    headline = f"{s.get('exposed', 0)} exposed / {s.get('total', 0)} relevant exclusion(s)"
    return (
        f"<h2>Coverage Exclusion Exposure — {_esc(headline)}</h2>"
        f"<table><thead><tr><th>Emerging exclusion</th><th>Lines</th><th>Status</th><th>Mitigation</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


_LIM_LABEL = {"no_coverage": "NO COVER", "shortfall": "SHORTFALL",
              "directional_low": "LOW", "not_carried": "NOT CARRIED", "ok": "OK"}
_LIM_CLASS = {"no_coverage": "lim-bad", "shortfall": "lim-bad", "directional_low": "lim-warn",
              "not_carried": "lim-muted", "ok": "lim-good"}


def _money(v) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v >= 1_000_000:
        n = v / 1_000_000
        return f"${n:.0f}M" if n == int(n) else f"${n:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


def _limit_section_html(review: Optional[dict]) -> str:
    """Optional limit-adequacy section: carried limits vs contract requirements +
    a directional baseline. Tenant clients only (needs carried/contract data)."""
    lines = (review or {}).get("lines") or []
    # only render lines that carry data or a requirement — skip empty noise
    rows_data = [l for l in lines if l.get("carried") or l.get("contract_required") or l.get("status") == "directional_low"]
    if not rows_data:
        return ""
    s = review.get("summary") or {}
    rows = ""
    for l in rows_data:
        c = l.get("carried") or {}
        req = l.get("contract_required") or {}
        base = l.get("baseline") or {}
        carried_s = (_money(c.get("per_occurrence")) + (f" / {_money(c.get('aggregate'))}" if c.get("aggregate") else "")) if l.get("carried") else "—"
        req_s = (_money(req.get("per_occurrence")) + (f" / {_money(req.get('aggregate'))}" if req.get("aggregate") else "")) if req else "—"
        rows += (
            f"<tr><td>{_esc(l.get('label'))}</td><td class='r'>{carried_s}</td>"
            f"<td class='r'>{req_s}</td><td class='r'>{_money(base.get('per_occurrence')) if base else '—'}</td>"
            f"<td class='{_LIM_CLASS.get(l.get('status'), 'lim-muted')}'>{_LIM_LABEL.get(l.get('status'), '')}</td>"
            f"<td>{_esc(l.get('gap'))}</td></tr>"
        )
        eg = l.get("endorsement_gaps") or []
        if eg:
            rows += (f"<tr class='note'><td colspan='6'>Required endorsements to confirm: "
                     f"{_esc(', '.join(e['label'] for e in eg))}</td></tr>")
    headline = f"{s.get('contract_shortfalls', 0)} contract shortfall(s) / {s.get('contracts', 0)} contract(s) reviewed"
    return (
        f"<h2>Limit Adequacy &amp; Contract Review — {_esc(headline)}</h2>"
        f"<table><thead><tr><th>Line</th><th class='r'>Carried</th><th class='r'>Contract req.</th>"
        f"<th class='r'>Baseline</th><th>Status</th><th>Gap</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _loss_section_html(tri: Optional[dict]) -> str:
    """Optional loss-development section: per policy period, latest reported
    incurred vs chain-ladder ultimate + adverse development. Shows reserve
    adequacy — claims that develop upward read as higher ultimate cost."""
    lines = [ln for ln in ((tri or {}).get("lines") or []) if ln.get("periods")]
    if not lines:
        return ""
    out = ""
    for ln in lines:
        s = ln["summary"]
        if s.get("valuations", 0) < 2 and s.get("total_adverse_development", 0) == 0:
            # single valuation — show reported only, no projection
            rows = "".join(
                f"<tr><td>{_esc(p['period_label'])}</td><td class='r'>{_money(p['latest_incurred'])}</td>"
                f"<td class='r'>—</td><td class='r'>—</td></tr>" for p in ln["periods"]
            )
        else:
            rows = "".join(
                f"<tr><td>{_esc(p['period_label'])}</td><td class='r'>{_money(p['latest_incurred'])}</td>"
                f"<td class='r'>{_money(p['ultimate'])}</td>"
                f"<td class='r {'lim-bad' if p['adverse_development'] > 0 else 'lim-good'}'>"
                f"{('+' if p['adverse_development'] > 0 else '')}{_money(p['adverse_development'])}</td></tr>"
                for p in ln["periods"]
            )
        head = (f"{_esc(ln['label'])} — reported incurred → projected ultimate "
                f"({'+' if s['total_adverse_development'] > 0 else ''}{_money(s['total_adverse_development'])} "
                f"adverse, {s['adverse_pct']}% over {s['valuations']} valuation(s))")
        out += (f"<h2>Loss Development — {head}</h2>"
                f"<table><thead><tr><th>Policy period</th><th class='r'>Reported incurred</th>"
                f"<th class='r'>Projected ultimate</th><th class='r'>Adverse dev.</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>")
    return out


_CAT_CLASS = {"severe": "vt-severe", "high": "vt-high", "elevated": "vt-elev",
              "moderate": "vt-mod", "low": "vt-low"}


def _property_section_html(prop: Optional[dict]) -> str:
    """Optional commercial-property section: TIV, COPE grade, insurance-to-value, and
    worst catastrophe tier. Renders nothing when there are no buildings."""
    if not prop:
        return ""
    rollup = prop.get("rollup") or {}
    bc = rollup.get("building_count") or prop.get("building_count") or 0
    if not bc:
        return ""
    tiv = rollup.get("tiv") if rollup.get("tiv") is not None else prop.get("total_tiv")
    cope = rollup.get("avg_cope_score")
    worst_cope = rollup.get("worst_cope_grade")
    itv = rollup.get("itv") or {}
    ratio = itv.get("portfolio_ratio")
    under = itv.get("under_count") or 0
    worst_cat = (prop.get("cat") or {}).get("worst_tier") or prop.get("worst_cat_tier")
    cat_cls = _CAT_CLASS.get(worst_cat or "", "vt-unk")
    itv_s = f"{round(ratio * 100)}%" if ratio is not None else "—"
    cope_s = f"{cope}{' / ' + worst_cope if worst_cope else ''}" if cope is not None else "—"
    under_note = (f"<div class='narr'>{under} building(s) below the 90% insurance-to-value floor — "
                  f"coinsurance-penalty exposure.</div>" if under else "")
    return (
        f"<h2>Commercial Property — {bc} building(s), {_money(tiv) if tiv else '—'} TIV</h2>"
        f"<div class='grid'>"
        f"<div class='cell'><div class='l'>TIV</div><div class='v'>{_money(tiv) if tiv else '—'}</div></div>"
        f"<div class='cell'><div class='l'>COPE</div><div class='v'>{_esc(cope_s)}</div></div>"
        f"<div class='cell'><div class='l'>Ins-to-value</div><div class='v'>{itv_s}</div></div>"
        f"<div class='cell'><div class='l'>Cat exposure</div><div class='v {cat_cls}'>{_esc((worst_cat or '—').upper())}</div></div>"
        f"</div>{under_note}"
    )


def _packet_html(ctx: dict) -> str:
    wc = ctx.get("wc") or {}
    epl = ctx.get("epl") or {}
    sr = wc.get("state_rate") or {}
    bench = wc.get("benchmark") or {}

    epl_rows = "".join(
        f"<tr><td>{_esc(f.get('label'))}</td><td class='r'>{_esc(f.get('score'))}</td>"
        f"<td class='st {f.get('status')}'>{_esc((f.get('status') or '').upper())}</td></tr>"
        for f in (epl.get("factors") or [])
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }}
      h1 {{ color:#1f8a5b; margin:0 0 2px; font-size:22px; }}
      .sub {{ color:#666; margin:0 0 16px; }}
      h2 {{ font-size:13px; border-bottom:2px solid #1f8a5b; padding-bottom:4px; margin:18px 0 8px; }}
      .grid {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
      .cell {{ border:1px solid #e5e7eb; border-radius:8px; padding:8px 12px; min-width:110px; }}
      .cell .l {{ font-size:8px; text-transform:uppercase; letter-spacing:.6px; color:#888; }}
      .cell .v {{ font-size:18px; font-weight:300; font-family:monospace; margin-top:3px; }}
      table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
      th {{ text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:4px 6px; }}
      td {{ padding:4px 6px; border-bottom:1px solid #f0f0f0; }}
      td.r {{ text-align:right; font-family:monospace; }}
      .st {{ font-size:8px; font-weight:700; }} .st.strong{{color:#1f8a5b}} .st.partial{{color:#b8902f}} .st.gap{{color:#b23b3b}} .st.na{{color:#999}}
      .narr {{ background:#f1f6f3; border-left:3px solid #1f8a5b; padding:10px 14px; border-radius:0 6px 6px 0; margin:8px 0; }}
      .ready {{ background:#fff8ec; border-left:3px solid #b8902f; padding:8px 12px; border-radius:0 6px 6px 0; margin:10px 0; font-size:10px; }}
      .ready ul {{ margin:4px 0 0; padding-left:16px; }} .rfix {{ color:#666; margin-top:4px; }}
      .vt {{ font-size:8px; font-weight:700; }} .vt-severe,.vt-high{{color:#b23b3b}} .vt-elev{{color:#b8902f}} .vt-mod,.vt-low{{color:#1f8a5b}} .vt-unk{{color:#999}}
      .ex-exposed{{color:#b23b3b;font-weight:700}} .ex-monitor{{color:#b8902f;font-weight:700}} .ex-mitigated{{color:#1f8a5b;font-weight:700}}
      .lim-good{{color:#1f8a5b;font-weight:700;font-size:8px}} .lim-warn{{color:#b8902f;font-weight:700;font-size:8px}} .lim-bad{{color:#b23b3b;font-weight:700;font-size:8px}} .lim-muted{{color:#999;font-weight:700;font-size:8px}}
      tr.note td {{ font-size:9px; color:#666; background:#fafafa; }}
      .foot {{ margin-top:24px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }}
    </style></head><body>
      <h1>Underwriting Submission</h1>
      <p class="sub">{_esc(ctx.get('name'))} — {_esc(ctx.get('industry'))} · {_esc(ctx.get('headcount'))} employees · {_esc(ctx.get('state'))}</p>

      {_readiness_section_html(ctx.get('readiness'))}

      <h2>Workers' Compensation</h2>
      <div class="grid">
        <div class="cell"><div class="l">TRIR</div><div class="v">{_esc(wc.get('trir'))}</div></div>
        <div class="cell"><div class="l">DART</div><div class="v">{_esc(wc.get('dart_rate'))}</div></div>
        <div class="cell"><div class="l">Industry bench</div><div class="v">{_esc(bench.get('trir'))}</div></div>
        <div class="cell"><div class="l">Experience mod</div><div class="v">{_esc(f"{wc['current_emr']:.2f}" if wc.get('current_emr') is not None else None)}</div></div>
        <div class="cell"><div class="l">Recordables</div><div class="v">{_esc(wc.get('recordable_cases'))}</div></div>
        <div class="cell"><div class="l">State rate {_esc(ctx.get('state'))}</div><div class="v">{_esc((f"{sr['loss_cost_change_pct']:+.1f}%" if sr.get('loss_cost_change_pct') is not None else None))}</div></div>
      </div>
      <div class="narr">{_esc(_wc_narrative(ctx))}</div>

      <h2>EPL Readiness — {_esc(epl.get('score'))}/100 ({_esc((epl.get('band') or '').title())})</h2>
      <table><thead><tr><th>Factor</th><th class="r">Score</th><th>Status</th></tr></thead><tbody>{epl_rows or '<tr><td>No EPL data</td><td></td><td></td></tr>'}</tbody></table>
      <div class="narr">{_esc(_epl_narrative(ctx))}</div>

      {_controls_section_html(ctx.get('controls'))}

      {_venue_section_html(ctx.get('venue'))}

      {_exclusions_section_html(ctx.get('exclusions'))}

      {_limit_section_html(ctx.get('limits'))}

      {_property_section_html(ctx.get('property'))}

      {_loss_section_html(ctx.get('loss_development'))}

      <div class="foot">Prepared by Matcha for broker submission. Risk metrics derived from the client's safety/HR records;
      state WC rate trends are headline estimates pending a licensed NCCI feed. Present alongside the carrier loss run.</div>
    </body></html>"""


async def render_submission_pdf(context: dict) -> bytes:
    def _render() -> bytes:
        from weasyprint import HTML, default_url_fetcher

        def _no_net(url: str):
            if url.startswith("data:"):
                return default_url_fetcher(url)
            raise ValueError("network fetching disabled for submission PDF")

        return HTML(string=_packet_html(context), url_fetcher=_no_net).write_pdf()

    return await asyncio.to_thread(_render)
