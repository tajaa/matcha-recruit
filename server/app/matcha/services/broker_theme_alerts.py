"""Broker theme alerts — turn the client's IR "risk themes" (the Themes & People
tab) into broker Action-Center alerts with a prescriptive, broker-voiced
suggestion. Complements the quantitative trend alerts (TRIR/DART/lost-days) with
the *qualitative* hotspots ("catastrophic forklift maintenance failures at
Sherman Oaks") underwriters and brokers actually act on.

Themes are reused from the same `ir_company_analysis` cache the risk-insights
endpoint writes (24h TTL); generated on demand for the broker's clients if stale.
Pure helpers (`evaluate_theme_alerts`, `_slug`, severity map) are unit-tested.
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_analyzer = None  # cached IRAnalyzer (for the broker-suggestion one-shot)


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from app.config import get_settings
        from app.matcha.services.ir_analysis import IRAnalyzer
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer

# Broker theme alerts use a trailing-quarter window (more incidents → better
# underwriting themes than the FE's 30d default). Shares ir_company_analysis with
# the risk-insights endpoint when it's viewed at days=90; own 24h cache otherwise.
_SCOPE_KEY = "loc=all:days=90"
_THEME_DAYS = 90
_CACHE_TTL = timedelta(hours=24)

# Theme severity → broker alert severity. medium/low don't alert.
THEME_SEVERITY_MAP = {"critical": "critical", "high": "warning"}
MAX_THEME_ALERTS_PER_CLIENT = 4


def _slug(label: str, location_name: Optional[str]) -> str:
    """Stable metric_key suffix for a theme (so dedup + cooldown work across runs)."""
    basis = f"{(label or '').lower().strip()}|{(location_name or '').lower().strip()}"
    norm = re.sub(r"[^a-z0-9]+", "-", basis).strip("-")
    short = norm[:24]  # metric_key is varchar(40): 'theme:'(6)+24+'-'(1)+6 = 37
    h = hashlib.sha1(basis.encode()).hexdigest()[:6]
    return f"theme:{short}-{h}"


def evaluate_theme_alerts(themes: list[dict]) -> list[dict]:
    """Pure: filter themes to alert-worthy (high/critical) candidates.

    Each candidate: {metric_key, severity, incident_count, message, theme_label,
    location_name, insight, recommendation}. Message reads as the alert headline.
    """
    out: list[dict] = []
    for t in themes or []:
        sev = THEME_SEVERITY_MAP.get((t.get("severity") or "").lower())
        if not sev:
            continue
        label = (t.get("label") or "").strip()
        if not label:
            continue
        loc = (t.get("location_name") or "").strip() or None
        count = int(t.get("incident_count") or 0)
        # Only append the location if the model didn't already bake it into the label.
        headline = label if (loc and loc.lower() in label.lower()) or not loc else f"{label} at {loc}"
        out.append({
            "metric_key": _slug(label, loc),
            "severity": sev,
            "incident_count": count,
            "theme_label": label,
            "location_name": loc,
            "insight": (t.get("insight") or "").strip() or None,
            "recommendation": (t.get("recommendation") or "").strip() or None,
            "message": f"Recurring risk theme — {headline} ({count} incident{'s' if count != 1 else ''}).",
        })
    # Critical first, then by incident volume; cap so the digest stays focused.
    out.sort(key=lambda c: (c["severity"] != "critical", -c["incident_count"]))
    return out[:MAX_THEME_ALERTS_PER_CLIENT]


async def fetch_or_generate_themes(conn, company_id: UUID) -> list[dict]:
    """Read the cached risk-insights themes for a company; generate + cache if
    stale/absent. FastAPI context (pool available — theme detection's rate limiter
    needs it, so this can't run in the pool-free worker). Never raises → [] on fail."""
    try:
        cached = await conn.fetchrow(
            "SELECT analysis_data, generated_at FROM ir_company_analysis "
            "WHERE company_id = $1 AND analysis_type = 'risk_insights' AND scope_key = $2",
            company_id, _SCOPE_KEY,
        )
        if cached and (datetime.utcnow() - cached["generated_at"]) < _CACHE_TTL:
            payload = cached["analysis_data"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return payload.get("themes", []) if isinstance(payload, dict) else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[theme-alerts] cache read failed for %s: %s", company_id, exc)

    # Generate fresh.
    try:
        start = datetime.utcnow() - timedelta(days=_THEME_DAYS)
        incident_rows = await conn.fetch(
            """
            SELECT id, occurred_at, incident_type, severity, location_id,
                   description, root_cause, witnesses, involved_employee_ids, er_case_id
            FROM ir_incidents
            WHERE company_id = $1 AND occurred_at >= $2
            ORDER BY occurred_at DESC LIMIT 200
            """,
            company_id, start,
        )
        if not incident_rows:
            return []
        loc_rows = await conn.fetch(
            "SELECT id, name, city, state FROM business_locations WHERE company_id = $1 AND is_active = true",
            company_id,
        )
        location_lookup: dict[str, str] = {}
        for lr in loc_rows:
            label = (lr["name"] or "").strip() or ", ".join(p for p in (lr["city"], lr["state"]) if p) or str(lr["id"])[:8]
            location_lookup[str(lr["id"])] = label
        company_row = await conn.fetchrow("SELECT name, industry FROM companies WHERE id = $1", company_id)
        company_context = None
        if company_row:
            company_context = " — ".join([company_row["name"]] + (
                [f"Industry: {company_row['industry']}"] if company_row["industry"] else []))

        from app.matcha.services.ir_analysis import get_ir_analyzer
        analyzer = get_ir_analyzer()
        result = await analyzer.detect_risk_themes(
            incidents=[dict(r) for r in incident_rows],
            location_lookup=location_lookup,
            employee_lookup=None,
            company_context=company_context,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[theme-alerts] theme generation failed for %s: %s", company_id, exc)
        return []

    themes: list[dict] = []
    for t in result.get("themes", []):
        loc_id = t.get("location_id")
        try:
            themes.append({
                "label": t["label"], "severity": t["severity"],
                "location_id": loc_id, "location_name": location_lookup.get(loc_id) if loc_id else None,
                "incident_count": int(t["incident_count"]),
                "evidence_incident_ids": [str(e) for e in t.get("evidence_incident_ids", [])],
                "insight": t["insight"], "recommendation": t["recommendation"],
            })
        except (KeyError, ValueError, TypeError):
            continue

    payload = {"period_days": _THEME_DAYS, "generated_at": datetime.utcnow().isoformat(),
               "location_id": None, "themes": themes, "from_cache": False}
    try:
        await conn.execute(
            """
            INSERT INTO ir_company_analysis (company_id, analysis_type, scope_key, analysis_data)
            VALUES ($1, 'risk_insights', $2, $3)
            ON CONFLICT (company_id, analysis_type, scope_key)
            DO UPDATE SET analysis_data = $3, generated_at = NOW()
            """,
            company_id, _SCOPE_KEY, json.dumps(payload, default=str),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[theme-alerts] cache write failed for %s: %s", company_id, exc)
    return themes


_SUGGEST_PROMPT = """You are advising an insurance BROKER about a client's recurring workplace-risk theme.
Write ONE concrete, broker-voiced action the broker can offer the client to mitigate it (e.g.
"Provide audit guidance for the facility's maintenance logs and safety training for management
oversight" or "Offer materials for retraining staff on proper high-density storage procedures").

Client: {company}
Theme: {label}{loc}
Insight: {insight}
Client-facing recommendation (rephrase for the broker, don't copy): {rec}

Return ONLY JSON: {{"suggestion": "<one broker action, ~15-30 words>"}}"""


async def broker_suggestion(theme: dict, company_name: Optional[str]) -> Optional[str]:
    """Best-effort broker-voiced suggestion for a theme. Falls back to the theme's
    own recommendation. Never raises."""
    fallback = theme.get("recommendation")
    try:
        analyzer = _get_analyzer()
        prompt = _SUGGEST_PROMPT.format(
            company=company_name or "the client", label=theme.get("theme_label") or "",
            loc=f" at {theme['location_name']}" if theme.get("location_name") else "",
            insight=theme.get("insight") or "", rec=fallback or "",
        )
        resp = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=prompt),
            timeout=30,
        )
        parsed = analyzer._parse_json_response((getattr(resp, "text", None) or "").strip()) or {}
        s = parsed.get("suggestion")
        if isinstance(s, str) and s.strip():
            return s.strip()
    except Exception as exc:  # noqa: BLE001
        logger.info("[theme-alerts] broker suggestion fell back: %s", exc)
    return fallback


async def scan_broker_theme_alerts(broker_id: UUID) -> dict:
    """Regenerate theme alerts for all of a broker's active clients and upsert them
    into broker_risk_alerts (metric_key 'theme:*', extras in metadata). Runs in
    FastAPI (pool available). Idempotent; preserves is_read on re-scan; resolves
    themes that no longer fire. Returns {clients_scanned, theme_alerts}."""
    from app.database import get_connection
    from app.matcha.dependencies import BROKER_ACTIVE_LINK_STATUSES

    async with get_connection() as conn:
        links = await conn.fetch(
            """
            SELECT l.company_id, c.name AS company_name
            FROM broker_company_links l
            JOIN companies c ON c.id = l.company_id
            WHERE l.broker_id = $1 AND l.status = ANY($2::text[])
              AND COALESCE(c.status, 'approved') NOT IN ('pending', 'rejected')
            """,
            broker_id, list(BROKER_ACTIVE_LINK_STATUSES),
        )

    clients_scanned = 0
    theme_alerts = 0
    for link in links:
        company_id = link["company_id"]
        clients_scanned += 1
        async with get_connection() as conn:
            try:
                themes = await fetch_or_generate_themes(conn, company_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[theme-alerts] scan: themes failed for %s: %s", company_id, exc)
                themes = []
            candidates = evaluate_theme_alerts(themes)

            existing = await conn.fetch(
                "SELECT metric_key, metadata FROM broker_risk_alerts "
                "WHERE broker_id = $1 AND company_id = $2 AND metric_key LIKE 'theme:%'",
                broker_id, company_id,
            )
            existing_by = {r["metric_key"]: r for r in existing}
            fired: set = set()

            for c in candidates:
                fired.add(c["metric_key"])
                # reuse a prior suggestion so re-scans don't re-hit Gemini
                prior_meta = (existing_by.get(c["metric_key"]) or {}).get("metadata")
                if isinstance(prior_meta, str):
                    try:
                        prior_meta = json.loads(prior_meta)
                    except Exception:
                        prior_meta = None
                sugg = (prior_meta or {}).get("suggestion") if isinstance(prior_meta, dict) else None
                if not sugg:
                    sugg = await broker_suggestion(c, link["company_name"])
                meta = {
                    "kind": "theme", "theme_label": c["theme_label"], "location_name": c["location_name"],
                    "incident_count": c["incident_count"], "insight": c["insight"],
                    "recommendation": c["recommendation"], "suggestion": sugg,
                }
                await conn.execute(
                    """
                    INSERT INTO broker_risk_alerts
                        (broker_id, company_id, metric_key, severity, current_value, message, metadata,
                         first_alerted_at, last_alerted_at, last_evaluated_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb, NOW(), NOW(), NOW())
                    ON CONFLICT (broker_id, company_id, metric_key) DO UPDATE SET
                        severity = EXCLUDED.severity, current_value = EXCLUDED.current_value,
                        message = EXCLUDED.message, metadata = EXCLUDED.metadata,
                        resolved_at = NULL, last_evaluated_at = NOW()
                    """,
                    broker_id, company_id, c["metric_key"], c["severity"],
                    c["incident_count"], c["message"], json.dumps(meta),
                )
                theme_alerts += 1

            # Resolve theme rows that no longer fire.
            for mk in existing_by:
                if mk not in fired:
                    await conn.execute(
                        "UPDATE broker_risk_alerts SET resolved_at = NOW(), last_evaluated_at = NOW() "
                        "WHERE broker_id = $1 AND company_id = $2 AND metric_key = $3 AND resolved_at IS NULL",
                        broker_id, company_id, mk,
                    )

    return {"clients_scanned": clients_scanned, "theme_alerts": theme_alerts}
