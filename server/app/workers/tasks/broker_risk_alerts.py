"""Celery task: broker negative-trend risk alerts.

Periodic (re-dispatched on every worker startup ~15 min, gated by the
`broker_risk_alerts` row in scheduler_settings). For each active broker→client
link it recomputes the client's trailing-12mo WC/safety metrics, detects any
metric that worsened vs the prior 12 months, de-dupes against the
`broker_risk_alerts` state table (14-day cooldown + re-arm on resolve), and
emails each broker ONE digest of its newly-firing clients.

Trend rules + the cooldown decision are pure functions (`evaluate_trends`,
`decide_action`) so they can be unit-tested without a DB or worker.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from ..celery_app import celery_app
from ..utils import get_db_connection

# ── Tunables (code constants per design; no per-broker settings UI) ──────────
COOLDOWN_DAYS = 1               # re-email once per day until broker marks viewed
CRITICAL_MULTIPLIER = 2.0  # delta >= threshold × this → severity "critical"
PREMIUM_CRITICAL_DOLLARS = 25_000  # est. annual premium impact → critical

THRESHOLDS = {
    "trir_delta_pct": 15.0,
    "trir_abs_min_rise": 0.5,
    "dart_delta_pct": 20.0,
    "dart_abs_min_rise": 0.5,
    "lost_days_delta_pct": 25.0,
    "lost_days_abs_min_rise": 5,
    "premium_worsen_pct": 20.0,
}

# Recipient roles within a broker org.
RECIPIENT_ROLES = ("owner", "admin")

# Sentinel "never alerted" timestamp — rows pending a (not-yet-sent) email get
# this so a failed send is retried next cycle; bumped to NOW() only on success.
_EPOCH = datetime(1970, 1, 1)


# ── Pure trend detection ─────────────────────────────────────────────────────
def should_suppress(metrics: dict) -> bool:
    """True when the population is too thin for RATE metrics (TRIR/DART/premium)
    to be meaningful. Count metrics (lost days, claim-free) ignore this."""
    dq = metrics.get("data_quality") or {}
    if dq.get("insufficient_population"):
        return True
    if dq.get("headcount_missing"):
        return True
    if not metrics.get("headcount"):
        return True
    return False


def _severity_for_delta(delta_pct: Optional[float], threshold: float) -> str:
    if delta_pct is not None and delta_pct >= threshold * CRITICAL_MULTIPLIER:
        return "critical"
    return "warning"


def evaluate_trends(
    metrics: dict,
    *,
    prior_premium_direction: Optional[str] = None,
    prior_premium_dollars: Optional[float] = None,
) -> list[dict]:
    """Return alert candidates for one company's metrics.

    Each candidate: {metric_key, severity, current_value, prior_value,
    delta_pct, premium_direction, message}. Empty list = nothing worth alerting.

    Rate-based metrics (TRIR, DART, premium impact) are suppressed when the
    population is too thin for them to be statistically meaningful. Count-based
    metrics (lost workdays, claim-free streak) need no hours estimate and fire
    regardless of headcount.
    """
    th = THRESHOLDS
    prior = metrics.get("prior") or {}
    rates_unreliable = should_suppress(metrics)
    out: list[dict] = []

    # TRIR — recordable incident rate up.
    trir, ptrir = metrics.get("trir"), prior.get("trir")
    d = prior.get("trir_delta_pct")
    if (
        not rates_unreliable
        and trir is not None and ptrir is not None and d is not None
        and d >= th["trir_delta_pct"] and (trir - ptrir) >= th["trir_abs_min_rise"]
    ):
        out.append({
            "metric_key": "trir",
            "severity": _severity_for_delta(d, th["trir_delta_pct"]),
            "current_value": trir, "prior_value": ptrir, "delta_pct": d,
            "premium_direction": None,
            "message": f"TRIR rose {d:.0f}% over the trailing year ({ptrir} → {trir}).",
        })

    # DART rate up.
    dart, pdart = metrics.get("dart_rate"), prior.get("dart_rate")
    dd = prior.get("dart_delta_pct")
    if (
        not rates_unreliable
        and dart is not None and pdart is not None and dd is not None
        and dd >= th["dart_delta_pct"] and (dart - pdart) >= th["dart_abs_min_rise"]
    ):
        out.append({
            "metric_key": "dart",
            "severity": _severity_for_delta(dd, th["dart_delta_pct"]),
            "current_value": dart, "prior_value": pdart, "delta_pct": dd,
            "premium_direction": None,
            "message": f"DART rate rose {dd:.0f}% over the trailing year ({pdart} → {dart}).",
        })

    # Lost workdays up.
    ld, pld = metrics.get("lost_days"), prior.get("lost_days")
    ldd = prior.get("lost_days_delta_pct")
    if (
        ld is not None and pld is not None and ldd is not None
        and ldd >= th["lost_days_delta_pct"] and (ld - pld) >= th["lost_days_abs_min_rise"]
    ):
        out.append({
            "metric_key": "lost_days",
            "severity": _severity_for_delta(ldd, th["lost_days_delta_pct"]),
            "current_value": ld, "prior_value": pld, "delta_pct": ldd,
            "premium_direction": None,
            "message": f"Lost workdays rose {ldd:.0f}% over the trailing year ({pld} → {ld}).",
        })

    # Claim-free streak broken: clean prior window, recordable in current.
    rec, prec = metrics.get("recordable_cases"), prior.get("recordable_cases")
    if prec == 0 and rec and rec > 0:
        out.append({
            "metric_key": "claim_free_broken",
            "severity": "warning",
            "current_value": rec, "prior_value": 0, "delta_pct": None,
            "premium_direction": None,
            "message": (
                f"First recordable incident in 12+ months — "
                f"{rec} recordable case{'s' if rec != 1 else ''} this year ended a clean streak."
            ),
        })

    # Premium impact flips to "increase" (or worsens materially).
    pi = metrics.get("premium_impact") or {}
    if not rates_unreliable and pi.get("direction") == "increase":
        dollars = pi.get("annual_impact_dollars")
        flip = prior_premium_direction != "increase"
        worsened = (
            prior_premium_dollars is not None and prior_premium_dollars > 0
            and dollars is not None
            and dollars >= prior_premium_dollars * (1 + th["premium_worsen_pct"] / 100)
        )
        if flip or worsened:
            sev = "critical" if (dollars or 0) >= PREMIUM_CRITICAL_DOLLARS else "warning"
            out.append({
                "metric_key": "premium_increase",
                "severity": sev,
                "current_value": dollars, "prior_value": prior_premium_dollars,
                "delta_pct": None,
                "premium_direction": "increase",
                "message": (
                    f"Estimated WC premium impact now +${int(dollars):,}/yr and trending up."
                    if dollars is not None else
                    "Estimated WC premium impact trending toward an increase."
                ),
            })

    return out


def decide_action(existing: Optional[dict], candidate: dict, *, now: datetime) -> str:
    """Decide what to do with a candidate given its existing state-table row.

    Returns one of: 'insert' (new), 'send' (resend: re-arm / cooldown elapsed /
    escalation), 'skip' (still in cooldown OR already viewed — bump evaluated).

    Cadence policy: re-email once per day while the trend persists, UNTIL the
    broker marks the alert as viewed (`is_read = true`). After that we only
    re-email if severity escalates (warning → critical) or the alert resolves
    and re-arms.
    """
    if existing is None:
        return "insert"
    if existing.get("resolved_at") is not None:
        return "send"  # re-arm a previously-resolved alert
    escalated = candidate["severity"] == "critical" and existing.get("severity") != "critical"
    if existing.get("is_read"):
        return "send" if escalated else "skip"
    last = existing.get("last_alerted_at") or _EPOCH
    cooldown_elapsed = last < now - timedelta(days=COOLDOWN_DAYS)
    if cooldown_elapsed or escalated:
        return "send"
    return "skip"


# ── Async runner ─────────────────────────────────────────────────────────────
async def _run_broker_risk_alerts() -> dict:
    from app.core.services.email import EmailService
    from app.config import get_settings
    from app.matcha.routes.ir_incidents import compute_wc_metrics
    from app.matcha.dependencies import BROKER_ACTIVE_LINK_STATUSES

    conn = await get_db_connection()
    try:
        try:
            sched = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = 'broker_risk_alerts'"
            )
        except Exception:
            sched = None
        if not sched:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not sched["enabled"]:
            print("[Broker Risk Alerts] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        max_per_cycle = sched["max_per_cycle"] or 200  # caps brokers emailed
        now = datetime.utcnow()

        links = await conn.fetch(
            """
            SELECT l.broker_id, l.company_id, c.name AS company_name,
                   b.name AS broker_name
            FROM broker_company_links l
            JOIN companies c ON c.id = l.company_id
            JOIN brokers b ON b.id = l.broker_id
            WHERE l.status = ANY($1::text[])
              AND b.status = 'active'
              AND COALESCE(c.status, 'approved') NOT IN ('pending', 'rejected')
            ORDER BY l.broker_id
            """,
            list(BROKER_ACTIVE_LINK_STATUSES),
        )
        if not links:
            return {"evaluated": 0, "candidates": 0, "sent": 0}

        metrics_cache: dict = {}          # company_id -> metrics dict
        pending_by_broker: dict = {}      # broker_id -> {"name", "alerts":[...], "row_ids":[...]}
        n_candidates = 0
        n_resolved = 0
        n_skipped = 0

        for link in links:
            broker_id = link["broker_id"]
            company_id = link["company_id"]

            if company_id not in metrics_cache:
                try:
                    metrics_cache[company_id] = await compute_wc_metrics(conn, company_id)
                except Exception as exc:
                    print(f"[Broker Risk Alerts] metrics failed for company {company_id}: {exc}")
                    metrics_cache[company_id] = None
            metrics = metrics_cache[company_id]
            if not metrics:
                continue

            # Existing rows for this (broker, company) keyed by metric.
            existing_rows = await conn.fetch(
                "SELECT * FROM broker_risk_alerts WHERE broker_id = $1 AND company_id = $2",
                broker_id, company_id,
            )
            existing_by_metric = {r["metric_key"]: dict(r) for r in existing_rows}

            prior_prem = existing_by_metric.get("premium_increase")
            candidates = evaluate_trends(
                metrics,
                prior_premium_direction=(prior_prem or {}).get("premium_direction"),
                prior_premium_dollars=float((prior_prem or {}).get("current_value"))
                    if (prior_prem or {}).get("current_value") is not None else None,
            )
            fired_metrics = {c["metric_key"] for c in candidates}

            # Resolve rows whose rule no longer fires.
            for metric_key, row in existing_by_metric.items():
                if metric_key not in fired_metrics and row.get("resolved_at") is None:
                    await conn.execute(
                        "UPDATE broker_risk_alerts SET resolved_at = NOW(), last_evaluated_at = NOW() WHERE id = $1",
                        row["id"],
                    )
                    n_resolved += 1

            for cand in candidates:
                n_candidates += 1
                existing = existing_by_metric.get(cand["metric_key"])
                action = decide_action(existing, cand, now=now)

                cur = float(cand["current_value"]) if cand["current_value"] is not None else None
                prv = float(cand["prior_value"]) if cand["prior_value"] is not None else None
                dlt = float(cand["delta_pct"]) if cand["delta_pct"] is not None else None

                if action == "skip":
                    await conn.execute(
                        "UPDATE broker_risk_alerts SET last_evaluated_at = NOW() WHERE id = $1",
                        existing["id"],
                    )
                    n_skipped += 1
                    continue

                if action == "insert":
                    row_id = await conn.fetchval(
                        """
                        INSERT INTO broker_risk_alerts
                            (broker_id, company_id, metric_key, severity, current_value,
                             prior_value, delta_pct, premium_direction, message,
                             first_alerted_at, last_alerted_at, last_evaluated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, NOW(), 'epoch', NOW())
                        ON CONFLICT (broker_id, company_id, metric_key) DO UPDATE SET
                            severity = EXCLUDED.severity,
                            current_value = EXCLUDED.current_value,
                            prior_value = EXCLUDED.prior_value,
                            delta_pct = EXCLUDED.delta_pct,
                            premium_direction = EXCLUDED.premium_direction,
                            message = EXCLUDED.message,
                            resolved_at = NULL,
                            last_evaluated_at = NOW(),
                            is_read = false
                        RETURNING id
                        """,
                        broker_id, company_id, cand["metric_key"], cand["severity"],
                        cur, prv, dlt, cand["premium_direction"], cand["message"],
                    )
                else:  # action == "send" (re-arm / cooldown / escalation)
                    row_id = existing["id"]
                    await conn.execute(
                        """
                        UPDATE broker_risk_alerts SET
                            severity = $2, current_value = $3, prior_value = $4,
                            delta_pct = $5, premium_direction = $6, message = $7,
                            resolved_at = NULL, last_alerted_at = 'epoch',
                            last_evaluated_at = NOW(), is_read = false
                        WHERE id = $1
                        """,
                        row_id, cand["severity"], cur, prv, dlt,
                        cand["premium_direction"], cand["message"],
                    )

                bucket = pending_by_broker.setdefault(
                    broker_id, {"name": link["broker_name"], "alerts": [], "row_ids": []}
                )
                bucket["alerts"].append({
                    "company_name": link["company_name"],
                    "metric_key": cand["metric_key"],
                    "severity": cand["severity"],
                    "message": cand["message"],
                })
                bucket["row_ids"].append(row_id)

        if not pending_by_broker:
            return {"evaluated": len(metrics_cache), "candidates": n_candidates,
                    "sent": 0, "skipped": n_skipped, "resolved": n_resolved}

        settings = get_settings()
        email_service = EmailService()
        base_url = getattr(settings, "app_base_url", None) or getattr(settings, "frontend_url", "")
        portfolio_url = f"{base_url.rstrip('/')}/broker/risk-alerts" if base_url else None

        sent = 0
        for broker_id, bucket in list(pending_by_broker.items())[:max_per_cycle]:
            recipients = await conn.fetch(
                """
                SELECT u.email
                FROM broker_members bm
                JOIN users u ON u.id = bm.user_id
                WHERE bm.broker_id = $1 AND bm.is_active = true
                  AND bm.role = ANY($2::text[]) AND u.is_active = true
                """,
                broker_id, list(RECIPIENT_ROLES),
            )
            if not recipients:
                continue

            results = await asyncio.gather(*[
                email_service.send_broker_risk_alert_digest(
                    to_email=r["email"],
                    to_name=bucket["name"],
                    broker_name=bucket["name"],
                    alerts=bucket["alerts"],
                    portfolio_url=portfolio_url,
                )
                for r in recipients
            ], return_exceptions=True)

            if any(res is True for res in results):
                await conn.execute(
                    """
                    UPDATE broker_risk_alerts
                    SET last_alerted_at = NOW(),
                        first_alerted_at = COALESCE(first_alerted_at, NOW())
                    WHERE id = ANY($1::uuid[])
                    """,
                    bucket["row_ids"],
                )
                sent += 1

        return {"evaluated": len(metrics_cache), "candidates": n_candidates,
                "sent": sent, "skipped": n_skipped, "resolved": n_resolved}

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_broker_risk_alerts(self) -> dict:
    """Scan broker portfolios and email brokers about clients trending negative."""
    print("[Broker Risk Alerts] Running...")
    try:
        result = asyncio.run(_run_broker_risk_alerts())
        print(f"[Broker Risk Alerts] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[Broker Risk Alerts] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
