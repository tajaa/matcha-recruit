"""Universal controls-evidence register + proof-of-controls packet.

Generalizes the healthcare ``resident_care`` asset to ANY employer (WTW p.85
"mitigation-evidence systems of record … package for underwriters buys down
rate"). Auto-computes 8 controls from data Matcha already holds — reusing the
EPL-readiness factor engine for 5 and direct queries for 3 — then LEFT-merges
the per-control verification overrides in ``company_control_evidence``.
Deterministic PDF (WeasyPrint, SSRF-guarded). Never raises on the read path.
"""

import asyncio
import html
import logging
from uuid import UUID

from app.core.feature_flags import merge_company_features
from app.core.services.pdf import safe_url_fetcher

from . import epl_readiness, resident_care

logger = logging.getLogger(__name__)

# control_key → display label. First 5 reuse EPL-readiness factor keys + scores;
# last 3 are computed here (IR/OSHA, credentialing, safety programs). ``feature``
# (when present) flips a 0-score control to "na" when its backing feature is off,
# so a Lite tenant isn't shown a misleading "gap" for a feature it never had.
CONTROL_CATALOG = [
    {"key": "anti_harassment_policy", "label": "Anti-harassment / EEO policy", "source": "epl"},
    {"key": "harassment_training", "label": "Anti-harassment training", "source": "epl", "feature": "training"},
    {"key": "documented_discipline", "label": "Progressive discipline documentation", "source": "epl", "feature": "discipline"},
    {"key": "er_case_management", "label": "Employee-relations case management", "source": "epl", "feature": "er_copilot"},
    {"key": "wage_hour_compliance", "label": "Multi-state wage & hour compliance", "source": "epl"},
    {"key": "safety_incident_response", "label": "Safety incident response & documentation", "source": "ir", "feature": "incidents"},
    {"key": "credentialing_currency", "label": "Credentialing / license currency", "source": "credential"},
    {"key": "safety_programs", "label": "Safety & risk-management programs", "source": "safety"},
]

_EPL_KEYS = {f["key"] for f in CONTROL_CATALOG if f["source"] == "epl"}


def _band(score: int) -> str:
    if score >= 70:
        return "strong"
    if score >= 35:
        return "partial"
    return "gap"


async def _safety_incident_response(conn, company_id: UUID, features: dict) -> dict:
    """IR/OSHA incident-management evidence (last 24mo): documentation rate +
    recordable / return-to-work mix. Clean record (no incidents) reads strong."""
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE osha_recordable) AS recordable,
               COUNT(*) FILTER (WHERE COALESCE(corrective_actions,'') <> ''
                                  OR COALESCE(root_cause,'') <> '') AS documented,
               COUNT(*) FILTER (WHERE osha_recordable
                                  AND status NOT IN ('resolved','closed')
                                  AND return_to_work_date IS NULL) AS open_lost_time
        FROM ir_incidents
        WHERE company_id = $1 AND occurred_at >= CURRENT_DATE - INTERVAL '24 months'
        """,
        company_id,
    )
    total = int(row["total"] or 0)
    if total == 0:
        if not features.get("incidents"):
            return {"status": "na", "score": None, "metric": "Not tracked",
                    "detail": "Incident reporting not enabled"}
        return {"status": "strong", "score": 90, "metric": "0 incidents (24mo)",
                "detail": "No incidents recorded in the last 24 months"}
    documented = int(row["documented"] or 0)
    recordable = int(row["recordable"] or 0)
    open_lt = int(row["open_lost_time"] or 0)
    pct = round(100 * documented / total)
    return {
        "status": _band(pct), "score": pct, "metric": f"{pct}% documented",
        "detail": (f"{total} incident(s) / {recordable} recordable (24mo); "
                   f"{documented} with documented investigation; {open_lt} open lost-time"),
    }


async def _from_resident_summary(conn, company_id: UUID) -> dict:
    """Credentialing currency + safety-program inventory, reusing resident_care."""
    s = await resident_care.summary(conn, company_id)
    cred, prog = s["credentialing"], s["programs"]

    if cred["total"] == 0:
        credres = {"status": "na", "score": None, "metric": "Not tracked",
                   "detail": "No licensed-staff credentials tracked"}
    else:
        pct = cred["current_pct"]
        credres = {"status": _band(pct), "score": pct, "metric": f"{pct}% current",
                   "detail": f"{cred['total'] - cred['expired']}/{cred['total']} licensed staff current"}

    active = prog["active"]
    if prog["total"] == 0:
        progres = {"status": "na", "score": None, "metric": "None on file",
                   "detail": "No safety programs documented"}
    else:
        st = "strong" if active >= 3 else "partial" if active >= 1 else "gap"
        progres = {"status": st, "score": None, "metric": f"{active} active",
                   "detail": "Active: " + (", ".join(prog["active_types"]) or "none")}
    return {"credentialing_currency": credres, "safety_programs": progres}


async def build_register(conn, company_id: UUID, *, epl: dict | None = None) -> dict:
    """Auto-compute all 8 controls + merge verification overrides. Never raises.

    ``epl`` may be a precomputed ``compute_epl_readiness`` result (the broker
    submission path already has one) so we don't recompute it here.
    """
    company = await conn.fetchrow(
        "SELECT name, enabled_features, signup_source FROM companies WHERE id = $1", company_id
    )
    features = merge_company_features(
        company["enabled_features"] if company else None,
        signup_source=company["signup_source"] if company else None,
    )

    # 5 EPL-derived controls (reuse the readiness engine's per-factor output).
    try:
        if epl is None:
            epl = await epl_readiness.compute_epl_readiness(conn, company_id)
        fb = {f["key"]: f for f in (epl.get("factors") or [])}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("controls_evidence: EPL compute failed: %s", exc)
        fb = {}

    # 3 computed controls (best-effort; a failure degrades to "na").
    try:
        sir = await _safety_incident_response(conn, company_id, features)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("controls_evidence: safety_incident_response failed: %s", exc)
        sir = {"status": "na", "score": None, "metric": "—", "detail": "Unavailable"}
    try:
        rcvals = await _from_resident_summary(conn, company_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("controls_evidence: resident summary failed: %s", exc)
        rcvals = {
            "credentialing_currency": {"status": "na", "score": None, "metric": "—", "detail": "Unavailable"},
            "safety_programs": {"status": "na", "score": None, "metric": "—", "detail": "Unavailable"},
        }
    computed = {"safety_incident_response": sir, **rcvals}

    try:
        overrides = {
            r["control_key"]: r
            for r in await conn.fetch(
                "SELECT control_key, status, note, verified_at FROM company_control_evidence WHERE company_id = $1",
                company_id,
            )
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("controls_evidence: overrides fetch failed: %s", exc)
        overrides = {}

    controls: list[dict] = []
    for item in CONTROL_CATALOG:
        key = item["key"]
        if key in _EPL_KEYS:
            f = fb.get(key)
            if f is None:
                auto = {"status": "na", "score": None, "metric": "—", "detail": "No data"}
            else:
                status = f["status"]
                feat = item.get("feature")
                if feat and not features.get(feat) and (f.get("score") or 0) == 0:
                    status = "na"
                score = f.get("score")
                auto = {"status": status, "score": score,
                        "metric": (f"{score}/100" if score is not None else "—"),
                        "detail": f.get("detail")}
        else:
            auto = computed.get(key, {"status": "na", "score": None, "metric": "—", "detail": "No data"})

        ov = overrides.get(key)
        status = auto["status"]
        note = verified_at = None
        verified = False
        if ov:
            if ov["status"]:
                status = ov["status"]
            note = ov["note"]
            verified = ov["verified_at"] is not None
            verified_at = ov["verified_at"].isoformat() if ov["verified_at"] else None

        controls.append({
            "key": key, "label": item["label"], "source": item["source"],
            "status": status, "score": auto["score"],
            "metric": auto["metric"], "detail": auto["detail"],
            "override_status": ov["status"] if ov else None,
            "note": note, "verified": verified, "verified_at": verified_at,
        })

    summary = {
        "total": len(controls),
        "strong": sum(1 for c in controls if c["status"] == "strong"),
        "partial": sum(1 for c in controls if c["status"] == "partial"),
        "gap": sum(1 for c in controls if c["status"] == "gap"),
        "na": sum(1 for c in controls if c["status"] == "na"),
        "verified": sum(1 for c in controls if c["verified"]),
    }
    return {
        "company_id": str(company_id),
        "company_name": company["name"] if company else "Client",
        "controls": controls,
        "summary": summary,
    }


# --- proof-of-controls packet PDF (deterministic) --------------------------

def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


_STATUS_LABEL = {"strong": "STRONG", "partial": "PARTIAL", "gap": "GAP", "na": "N/A"}


def _controls_html(company_name: str, register: dict) -> str:
    rows = ""
    for c in register["controls"]:
        rows += (
            f"<tr><td>{_esc(c['label'])}</td>"
            f"<td class='st {c['status']}'>{_STATUS_LABEL.get(c['status'], c['status'].upper())}</td>"
            f"<td>{_esc(c['metric'])}</td>"
            f"<td>{'Verified' if c['verified'] else '—'}</td></tr>"
        )
        if c["note"]:
            rows += f"<tr class='note'><td colspan='4'>Note: {_esc(c['note'])}</td></tr>"

    s = register["summary"]
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }}
      h1 {{ color:#1f8a5b; margin:0 0 2px; font-size:22px; }}
      .sub {{ color:#666; margin:0 0 16px; }}
      h2 {{ font-size:13px; border-bottom:2px solid #1f8a5b; padding-bottom:4px; margin:18px 0 8px; }}
      .grid {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
      .cell {{ border:1px solid #e5e7eb; border-radius:8px; padding:8px 12px; min-width:90px; }}
      .cell .l {{ font-size:8px; text-transform:uppercase; letter-spacing:.6px; color:#888; }}
      .cell .v {{ font-size:18px; font-weight:300; font-family:monospace; margin-top:3px; }}
      table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
      th {{ text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:4px 6px; }}
      td {{ padding:4px 6px; border-bottom:1px solid #f0f0f0; }}
      .st {{ font-size:8px; font-weight:700; }}
      .st.strong{{color:#1f8a5b}} .st.partial{{color:#b8902f}} .st.gap{{color:#b23b3b}} .st.na{{color:#999}}
      tr.note td {{ font-size:9px; color:#666; background:#fafafa; border-bottom:1px solid #f0f0f0; }}
      .foot {{ margin-top:24px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }}
    </style></head><body>
      <h1>Proof of Controls — Risk Management Evidence</h1>
      <p class="sub">{_esc(company_name)} — prepared for prospective insurers</p>

      <h2>Controls summary</h2>
      <div class="grid">
        <div class="cell"><div class="l">Strong</div><div class="v">{_esc(s['strong'])}</div></div>
        <div class="cell"><div class="l">Partial</div><div class="v">{_esc(s['partial'])}</div></div>
        <div class="cell"><div class="l">Gap</div><div class="v">{_esc(s['gap'])}</div></div>
        <div class="cell"><div class="l">Verified</div><div class="v">{_esc(s['verified'])}/{_esc(s['total'])}</div></div>
      </div>

      <h2>Risk controls</h2>
      <table><thead><tr><th>Control</th><th>Status</th><th>Evidence</th><th>Verified</th></tr></thead>
        <tbody>{rows}</tbody></table>

      <div class="foot">Prepared by Matcha. Each control is auto-derived from the client's HR, safety, training,
      discipline, and compliance records; verified items were confirmed during a documented review. Present
      alongside the carrier loss run and insurance application.</div>
    </body></html>"""


async def render_controls_packet(company_name: str, register: dict) -> bytes:
    def _render() -> bytes:
        from weasyprint import HTML

        return HTML(string=_controls_html(company_name, register), url_fetcher=safe_url_fetcher).write_pdf()

    return await asyncio.to_thread(_render)
