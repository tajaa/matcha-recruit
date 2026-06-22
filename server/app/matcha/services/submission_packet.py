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
      .foot {{ margin-top:24px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }}
    </style></head><body>
      <h1>Underwriting Submission</h1>
      <p class="sub">{_esc(ctx.get('name'))} — {_esc(ctx.get('industry'))} · {_esc(ctx.get('headcount'))} employees · {_esc(ctx.get('state'))}</p>

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
