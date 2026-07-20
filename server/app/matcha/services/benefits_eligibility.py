"""Employee-benefits eligibility + renewal-risk engine.

Source-agnostic by design: a normalized ``benefit_roster_entries`` snapshot is
populated by EITHER a Finch sync OR a CSV upload, and every detector reads from
that store — so the cron, the broker endpoints, and the UI never care where the
data came from.

Scope 1 — Benefit Eligibility Alerts:
  * new_hire_enrollment_gap  — started ≤30d ago, still no benefits enrollment.
  * termination_premium_leak — terminated, but employer health premium still > $0.

Scope 2 — Cost Early-Warning / Renewal Risk:
  * combines roster turnover with Matcha incident/safety logs (lost workdays,
    near misses, behavioral incidents) into a per-client / per-location risk band.

Nothing here runs DDL or holds long DB connections; callers own the connection.
"""
from __future__ import annotations

import csv
import html
import io
import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
NEW_HIRE_WINDOW_DAYS = 30          # enrollment window after start_date
NEW_HIRE_GRACE_DAYS = 40           # keep flagging (as "closed") a bit past the window
TERMINATION_LOOKBACK_DAYS = 120    # don't resurface ancient terminations
DEFAULT_EMPLOYER_PREMIUM = 650.0   # leak estimate when the exact amount is unknown

RISK_LOOKBACK_DAYS = 60            # separation / incident window
TURNOVER_SPIKE_PCT = 20.0         # ≥20% above baseline = turnover spike
INCIDENT_SPIKE_PCT = 15.0         # ≥15% above baseline = incident spike
DEFAULT_BASELINE_TURNOVER_PCT = 5.0   # first-run baseline (no history yet)

CSV_COLUMNS = [
    "external_id", "first_name", "last_name", "email", "department", "location",
    "start_date", "termination_date", "employment_status",
    "has_benefits_enrollment", "employer_health_premium_monthly", "gross_pay_period",
]


# ---------------------------------------------------------------------------
# Small coercion helpers
# ---------------------------------------------------------------------------

def _to_date(value) -> Optional[date]:
    if value in (None, "", "null"):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _to_bool(value) -> Optional[bool]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "t", "enrolled")


def _to_money(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return round(float(Decimal(str(value).replace("$", "").replace(",", "").strip())), 2)
    except (InvalidOperation, ValueError):
        return None


def _norm_status(value) -> str:
    s = (str(value or "").strip().lower())
    if s in ("inactive", "terminated", "separated", "false", "no"):
        return "inactive"
    return "active"


# ---------------------------------------------------------------------------
# Ingestion — populate benefit_roster_entries (source-agnostic)
# ---------------------------------------------------------------------------

async def ingest_roster_rows(conn, company_id: UUID, source: str, rows: list[dict]) -> int:
    """Upsert normalized roster rows. Each row carries the keys in CSV_COLUMNS
    plus optional ``benefit_line_items`` (list). Returns the number upserted."""
    count = 0
    for r in rows:
        external_id = (str(r.get("external_id") or "").strip()
                       or (r.get("email") or "").strip().lower()
                       or f"{r.get('first_name','')} {r.get('last_name','')}".strip())
        if not external_id:
            continue

        email = (r.get("email") or "").strip() or None
        employee_id = None
        if email:
            employee_id = await conn.fetchval(
                "SELECT id FROM employees WHERE org_id = $1 AND lower(email) = lower($2) LIMIT 1",
                company_id, email,
            )

        await conn.execute(
            """
            INSERT INTO benefit_roster_entries (
                company_id, source, external_id, employee_id,
                first_name, last_name, email, department, location,
                start_date, termination_date, employment_status,
                has_benefits_enrollment, employer_health_premium_monthly,
                gross_pay_period, benefit_line_items, snapshot_date, updated_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16::jsonb,CURRENT_DATE,NOW())
            ON CONFLICT (company_id, source, external_id) DO UPDATE SET
                employee_id = EXCLUDED.employee_id,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                email = EXCLUDED.email,
                department = EXCLUDED.department,
                location = EXCLUDED.location,
                start_date = EXCLUDED.start_date,
                termination_date = EXCLUDED.termination_date,
                employment_status = EXCLUDED.employment_status,
                has_benefits_enrollment = EXCLUDED.has_benefits_enrollment,
                employer_health_premium_monthly = EXCLUDED.employer_health_premium_monthly,
                gross_pay_period = EXCLUDED.gross_pay_period,
                benefit_line_items = EXCLUDED.benefit_line_items,
                snapshot_date = CURRENT_DATE,
                updated_at = NOW()
            """,
            company_id, source, external_id, employee_id,
            r.get("first_name"), r.get("last_name"), email,
            r.get("department"), r.get("location"),
            _to_date(r.get("start_date")), _to_date(r.get("termination_date")),
            _norm_status(r.get("employment_status")),
            _to_bool(r.get("has_benefits_enrollment")),
            _to_money(r.get("employer_health_premium_monthly")),
            _to_money(r.get("gross_pay_period")),
            json.dumps(r.get("benefit_line_items") or []),
        )
        count += 1
    return count


def parse_roster_csv(file_bytes: bytes) -> list[dict]:
    """Parse an uploaded roster CSV into normalized row dicts. Tolerant of
    extra/missing optional columns; ``external_id`` or ``email`` should be present."""
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    for raw in reader:
        norm = { (k or "").strip().lower().replace(" ", "_"): v for k, v in raw.items() }
        rows.append({col: norm.get(col) for col in CSV_COLUMNS})
    return rows


async def ingest_roster_from_csv(conn, company_id: UUID, file_bytes: bytes) -> int:
    rows = parse_roster_csv(file_bytes)
    return await ingest_roster_rows(conn, company_id, "csv", rows)


async def ingest_roster_from_finch(conn, company_id: UUID) -> int:
    """Best-effort Finch ingest. Returns 0 (no error) when the company has no
    Finch HRIS connection or the provider doesn't expose benefit facts."""
    from app.core.services.secret_crypto import decrypt_secret
    from app.matcha.services.hris_service import PROVIDER_HRIS
    from app.matcha.services.finch_service import get_finch_service

    connection = await conn.fetchrow(
        "SELECT * FROM integration_connections WHERE company_id = $1 AND provider = $2",
        company_id, PROVIDER_HRIS,
    )
    if not connection:
        return 0

    config = connection["config"] if isinstance(connection["config"], dict) else json.loads(connection["config"] or "{}")
    if config.get("mode") not in ("finch", "mock"):
        # Gusto/ADP read paths don't surface per-employee benefit deductions here.
        return 0

    secrets_raw = connection["secrets"] if isinstance(connection["secrets"], dict) else json.loads(connection["secrets"] or "{}")
    secrets: dict = {}
    for k, v in secrets_raw.items():
        if isinstance(v, str) and v:
            try:
                secrets[k] = decrypt_secret(v)
            except Exception:
                secrets[k] = v
        else:
            secrets[k] = v

    source = "mock" if config.get("mode") == "mock" else "finch"
    svc = get_finch_service()
    try:
        workers = await svc.fetch_workers(config, secrets)
        ids = [w.get("id") for w in workers if w.get("id")]
        facts = await svc.fetch_benefit_facts(config, secrets, ids)
    except Exception as exc:  # noqa: BLE001 — Finch is best-effort; CSV is the reliable path.
        logger.warning("benefits: Finch ingest failed for %s: %s", company_id, exc)
        return 0

    rows: list[dict] = []
    for w in workers:
        norm = svc.normalize_worker(w)
        fact = facts.get(w.get("id"), {})
        rows.append({
            "external_id": norm.get("hris_id"),
            "first_name": norm.get("first_name"),
            "last_name": norm.get("last_name"),
            "email": norm.get("email"),
            "department": norm.get("department"),
            "location": norm.get("work_city") or norm.get("work_state"),
            "start_date": norm.get("start_date"),
            "termination_date": norm.get("termination_date"),
            "employment_status": norm.get("employment_status"),
            "has_benefits_enrollment": fact.get("has_benefits_enrollment"),
            "employer_health_premium_monthly": fact.get("employer_health_premium_monthly"),
            "gross_pay_period": None,
            "benefit_line_items": [],
        })
    return await ingest_roster_rows(conn, company_id, source, rows)


# ---------------------------------------------------------------------------
# Scope 1 — eligibility-exception detection
# ---------------------------------------------------------------------------

def _full_name(row) -> str:
    name = f"{(row['first_name'] or '').strip()} {(row['last_name'] or '').strip()}".strip()
    return name or (row["email"] or row["external_id"] or "Unknown")


async def detect_eligibility_exceptions(conn, company_id: UUID) -> dict:
    """Recompute open eligibility exceptions for a company. Idempotent: refreshes
    metrics on existing rows, inserts new ones, and auto-resolves cleared ones."""
    today = date.today()
    entries = await conn.fetch(
        "SELECT * FROM benefit_roster_entries WHERE company_id = $1", company_id
    )

    detected: dict[str, dict] = {}
    for e in entries:
        start = e["start_date"]
        term = e["termination_date"]
        status = e["employment_status"]
        enrolled = e["has_benefits_enrollment"]
        premium = float(e["employer_health_premium_monthly"]) if e["employer_health_premium_monthly"] is not None else None

        # --- new-hire enrollment gap -------------------------------------
        if status == "active" and start is not None:
            days_elapsed = (today - start).days
            if 0 <= days_elapsed <= NEW_HIRE_GRACE_DAYS and enrolled is not True and not (premium and premium > 0):
                key = f"new_hire_enrollment_gap:{e['source']}:{e['external_id']}"
                detected[key] = {
                    "exception_type": "new_hire_enrollment_gap",
                    "reference_date": start,
                    "days_elapsed": days_elapsed,
                    "days_remaining": NEW_HIRE_WINDOW_DAYS - days_elapsed,
                    "estimated_monthly_leak": None,
                    "roster_entry_id": e["id"],
                    "employee_id": e["employee_id"],
                    "employee_name": _full_name(e),
                    "source": e["source"],
                }

        # --- terminated but still deducted (premium leak) ----------------
        is_terminated = status == "inactive" or term is not None
        still_deducted = (enrolled is True) or (premium is not None and premium > 0)
        if is_terminated and term is not None and still_deducted:
            days_elapsed = (today - term).days
            if 1 <= days_elapsed <= TERMINATION_LOOKBACK_DAYS:
                key = f"termination_premium_leak:{e['source']}:{e['external_id']}"
                detected[key] = {
                    "exception_type": "termination_premium_leak",
                    "reference_date": term,
                    "days_elapsed": days_elapsed,
                    "days_remaining": None,
                    "estimated_monthly_leak": premium if (premium and premium > 0) else DEFAULT_EMPLOYER_PREMIUM,
                    "roster_entry_id": e["id"],
                    "employee_id": e["employee_id"],
                    "employee_name": _full_name(e),
                    "source": e["source"],
                }

    # Upsert detected exceptions.
    for key, d in detected.items():
        await conn.execute(
            """
            INSERT INTO benefit_eligibility_exceptions (
                company_id, dedup_key, roster_entry_id, employee_id, employee_name,
                exception_type, reference_date, days_elapsed, days_remaining,
                estimated_monthly_leak, status, source, detected_at, last_seen_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'open',$11,NOW(),NOW())
            ON CONFLICT (company_id, dedup_key) DO UPDATE SET
                roster_entry_id = EXCLUDED.roster_entry_id,
                employee_id = EXCLUDED.employee_id,
                employee_name = EXCLUDED.employee_name,
                reference_date = EXCLUDED.reference_date,
                days_elapsed = EXCLUDED.days_elapsed,
                days_remaining = EXCLUDED.days_remaining,
                estimated_monthly_leak = EXCLUDED.estimated_monthly_leak,
                last_seen_at = NOW()
            """,
            company_id, key, d["roster_entry_id"], d["employee_id"], d["employee_name"],
            d["exception_type"], d["reference_date"], d["days_elapsed"], d["days_remaining"],
            d["estimated_monthly_leak"], d["source"],
        )

    # Auto-resolve open exceptions whose condition no longer holds.
    open_rows = await conn.fetch(
        "SELECT id, dedup_key FROM benefit_eligibility_exceptions WHERE company_id = $1 AND status = 'open'",
        company_id,
    )
    cleared = [r["id"] for r in open_rows if r["dedup_key"] not in detected]
    if cleared:
        await conn.execute(
            """
            UPDATE benefit_eligibility_exceptions
            SET status = 'resolved', resolved_at = NOW(),
                resolution_note = COALESCE(resolution_note, 'Auto-resolved: condition cleared')
            WHERE id = ANY($1::uuid[])
            """,
            cleared,
        )

    return {
        "detected": len(detected),
        "new_hire_gaps": sum(1 for d in detected.values() if d["exception_type"] == "new_hire_enrollment_gap"),
        "premium_leaks": sum(1 for d in detected.values() if d["exception_type"] == "termination_premium_leak"),
        "auto_resolved": len(cleared),
    }


# ---------------------------------------------------------------------------
# Scope 2 — renewal-risk computation
# ---------------------------------------------------------------------------

def _rel_delta(current: float, baseline: float) -> float:
    if baseline and baseline > 0:
        return round((current - baseline) / baseline * 100.0, 1)
    return 100.0 if current > 0 else 0.0


def _band(turnover_spike: bool, incident_spike: bool) -> str:
    if turnover_spike and incident_spike:
        return "critical"
    if turnover_spike or incident_spike:
        return "elevated"
    return "stable"


async def _incident_counts(conn, company_id: UUID, location: Optional[str]) -> dict:
    """Lost workdays + near misses + behavioral incidents in the lookback window.
    When ``location`` is given, fuzzy-match ir_incidents.location."""
    since = datetime.utcnow() - timedelta(days=RISK_LOOKBACK_DAYS)
    loc_clause = "AND location ILIKE $3" if location else ""
    params = [company_id, since] + ([f"%{location}%"] if location else [])
    row = await conn.fetchrow(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN osha_recordable = true
                              THEN COALESCE(days_away_from_work, 0) ELSE 0 END), 0) AS lost_workdays,
            COALESCE(SUM(CASE WHEN incident_type = 'near_miss' THEN 1 ELSE 0 END), 0) AS near_misses,
            COALESCE(SUM(CASE WHEN incident_type = 'behavioral' THEN 1 ELSE 0 END), 0) AS behavioral
        FROM ir_incidents
        WHERE company_id = $1 AND occurred_at >= $2 {loc_clause}
        """,
        *params,
    )
    return {
        "lost_workdays": int(row["lost_workdays"]),
        "near_misses": int(row["near_misses"]),
        "behavioral": int(row["behavioral"]),
    }


def _turnover(entries: list, today: date) -> tuple[int, int, float]:
    """(headcount, separations_in_window, turnover_pct) for a set of entries."""
    headcount = sum(1 for e in entries if e["employment_status"] == "active")
    separations = sum(
        1 for e in entries
        if e["termination_date"] is not None
        and 0 <= (today - e["termination_date"]).days <= RISK_LOOKBACK_DAYS
    )
    denom = max(headcount + separations, 1)
    return headcount, separations, round(separations / denom * 100.0, 1)


async def _upsert_risk_dimension(
    conn, company_id: UUID, dim_type: str, dim_value: str,
    entries: list, today: date,
) -> dict:
    headcount, separations, turnover_pct = _turnover(entries, today)
    location = dim_value if dim_type == "location" else None
    inc = await _incident_counts(conn, company_id, location) if dim_type in ("company", "location") else {
        "lost_workdays": 0, "near_misses": 0, "behavioral": 0,
    }
    gross = sum(float(e["gross_pay_period"]) for e in entries if e["gross_pay_period"] is not None) or None

    prior = await conn.fetchrow(
        """
        SELECT turnover_pct, lost_workdays FROM benefit_renewal_risk
        WHERE company_id = $1 AND dimension_type = $2 AND dimension_value = $3
        """,
        company_id, dim_type, dim_value,
    )
    turnover_baseline = float(prior["turnover_pct"]) if prior and prior["turnover_pct"] is not None else DEFAULT_BASELINE_TURNOVER_PCT
    lost_baseline = float(prior["lost_workdays"]) if prior and prior["lost_workdays"] is not None else 0.0

    turnover_delta = _rel_delta(turnover_pct, turnover_baseline)
    lost_delta = _rel_delta(float(inc["lost_workdays"]), lost_baseline)

    turnover_spike = turnover_delta >= TURNOVER_SPIKE_PCT and turnover_pct > 0
    incident_spike = (lost_delta >= INCIDENT_SPIKE_PCT and inc["lost_workdays"] > 0) or inc["near_misses"] > 0
    band = _band(turnover_spike, incident_spike)

    triggers: list[str] = []
    if turnover_spike:
        triggers.append(f"{turnover_pct:.0f}% turnover in last {RISK_LOOKBACK_DAYS}d ({turnover_delta:+.0f}% vs baseline)")
    if inc["lost_workdays"] > 0:
        triggers.append(f"{inc['lost_workdays']} lost-workday incident-days ({lost_delta:+.0f}% vs baseline)")
    if inc["near_misses"] > 0:
        triggers.append(f"{inc['near_misses']} near-miss reports")
    if inc["behavioral"] > 0:
        triggers.append(f"{inc['behavioral']} behavioral incidents")

    await conn.execute(
        """
        INSERT INTO benefit_renewal_risk (
            company_id, dimension_type, dimension_value, risk_band,
            turnover_pct, turnover_baseline_pct, turnover_delta_pct,
            lost_workdays, lost_workdays_baseline, lost_workdays_delta_pct,
            near_misses, behavioral_incidents, headcount, gross_payroll,
            triggers, computed_at, updated_at
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb,NOW(),NOW())
        ON CONFLICT (company_id, dimension_type, dimension_value) DO UPDATE SET
            risk_band = EXCLUDED.risk_band,
            turnover_pct = EXCLUDED.turnover_pct,
            turnover_baseline_pct = EXCLUDED.turnover_baseline_pct,
            turnover_delta_pct = EXCLUDED.turnover_delta_pct,
            lost_workdays = EXCLUDED.lost_workdays,
            lost_workdays_baseline = EXCLUDED.lost_workdays_baseline,
            lost_workdays_delta_pct = EXCLUDED.lost_workdays_delta_pct,
            near_misses = EXCLUDED.near_misses,
            behavioral_incidents = EXCLUDED.behavioral_incidents,
            headcount = EXCLUDED.headcount,
            gross_payroll = EXCLUDED.gross_payroll,
            triggers = EXCLUDED.triggers,
            computed_at = NOW(),
            updated_at = NOW()
        """,
        company_id, dim_type, dim_value, band,
        turnover_pct, turnover_baseline, turnover_delta,
        inc["lost_workdays"], lost_baseline, lost_delta,
        inc["near_misses"], inc["behavioral"], headcount, gross,
        json.dumps(triggers),
    )
    return {"risk_band": band, "triggers": triggers, "dimension_type": dim_type, "dimension_value": dim_value}


_BAND_RANK = {"critical": 0, "elevated": 1, "stable": 2}


async def compute_renewal_risk(conn, company_id: UUID) -> dict:
    """Recompute renewal-risk rows (company + per-department + per-location)."""
    today = date.today()
    entries = await conn.fetch(
        "SELECT * FROM benefit_roster_entries WHERE company_id = $1", company_id
    )
    entries = list(entries)

    results = [await _upsert_risk_dimension(conn, company_id, "company", "", entries, today)]

    by_location: dict[str, list] = {}
    by_department: dict[str, list] = {}
    for e in entries:
        if e["location"]:
            by_location.setdefault(e["location"], []).append(e)
        if e["department"]:
            by_department.setdefault(e["department"], []).append(e)

    for loc, rows in by_location.items():
        results.append(await _upsert_risk_dimension(conn, company_id, "location", loc, rows, today))
    for dept, rows in by_department.items():
        results.append(await _upsert_risk_dimension(conn, company_id, "department", dept, rows, today))

    worst = min((r["risk_band"] for r in results), key=lambda b: _BAND_RANK.get(b, 9), default="stable")
    return {"company_band": worst, "dimensions": len(results)}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def run_for_company(conn, company_id: UUID, *, use_finch: bool = True) -> dict:
    """Full pass for one company: optional Finch ingest → detect → risk."""
    ingested = 0
    if use_finch:
        try:
            ingested = await ingest_roster_from_finch(conn, company_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("benefits run_for_company finch ingest failed %s: %s", company_id, exc)
    exc_summary = await detect_eligibility_exceptions(conn, company_id)
    risk_summary = await compute_renewal_risk(conn, company_id)
    return {"company_id": str(company_id), "ingested": ingested, **exc_summary, "risk": risk_summary}


# ---------------------------------------------------------------------------
# Stabilization-Kit PDF (Scope 2 broker deliverable)
# ---------------------------------------------------------------------------

def _kit_html(company_name: str, detail: dict) -> str:
    # SSRF/HTML-injection guard: every free-text value below originates from
    # broker-uploaded CSV (location/department), company records, or computed
    # triggers — all HTML-escaped before interpolation so a value like
    # `<img src=http://169.254.169.254/...>` can't make WeasyPrint fetch it.
    # risk_band is a fixed enum (critical/elevated/stable); escaped anyway for
    # the class attribute. Numerics are format-specced, not user-controlled.
    rows = ""
    for d in detail.get("dimensions", []):
        if d["risk_band"] == "stable":
            continue
        band = html.escape(str(d["risk_band"]))
        triggers = "".join(f"<li>{html.escape(str(t))}</li>" for t in d.get("triggers", []))
        rows += f"""
        <div class="dim">
          <h3>{html.escape(d['dimension_type'].title())}: {html.escape(str(d['dimension_value'] or '(company-wide)'))}
              <span class="band {band}">{band.upper()}</span></h3>
          <p>Headcount {d['headcount']} · Turnover {d['turnover_pct']:.0f}% ({d['turnover_delta_pct']:+.0f}% vs baseline)</p>
          <ul>{triggers or '<li>No active triggers</li>'}</ul>
        </div>"""
    policy_line = f"Month {detail['policy_month']} of policy year" if detail.get("policy_month") else "Mid-policy review"
    return f"""<!DOCTYPE html><html><head><style>
      body {{ font-family: -apple-system, Helvetica, sans-serif; color:#1a1a1a; padding:32px; }}
      h1 {{ color:#0f766e; margin-bottom:0; }}
      .sub {{ color:#666; margin-top:4px; }}
      .dim {{ border:1px solid #e5e7eb; border-radius:8px; padding:14px 18px; margin:14px 0; }}
      .band {{ font-size:11px; padding:2px 8px; border-radius:10px; margin-left:8px; color:#fff; }}
      .band.critical {{ background:#dc2626; }} .band.elevated {{ background:#d97706; }}
      .rec {{ background:#f0fdfa; border-left:4px solid #0f766e; padding:14px 18px; margin-top:18px; }}
      ul {{ margin:6px 0; }}
    </style></head><body>
      <h1>Workforce Stabilization Kit</h1>
      <p class="sub">{html.escape(company_name)} — {policy_line} · Renewal exposure: {html.escape(str(detail.get('risk_band',''))).upper()}</p>
      {rows or '<p>No elevated locations or departments.</p>'}
      <div class="rec"><strong>Recommendation</strong><br/>{html.escape(str(detail.get('recommendation','')))}</div>
      <p class="sub" style="margin-top:28px;">Generated by Matcha — present alongside the underlying
      incident detail before renewal negotiations.</p>
    </body></html>"""


async def render_stabilization_kit_pdf(company_name: str, detail: dict) -> bytes:
    """Render the kit to PDF off the event loop (WeasyPrint, like the rest of the app)."""
    # Defense-in-depth against SSRF: the kit is built from semi-trusted
    # (broker-uploaded) data. render_pdf_async applies the shared safe fetcher
    # that refuses every remote/file scheme — only inline data: URIs resolve.
    from app.core.services.pdf import render_pdf_async

    return await render_pdf_async(_kit_html(company_name, detail))


def build_recommendation(detail_dimensions: list[dict]) -> str:
    """Plain-language recommendation derived from the elevated dimensions."""
    hot = [d for d in detail_dimensions if d.get("risk_band") in ("critical", "elevated")
           and d.get("dimension_type") in ("location", "department")]
    if not hot:
        return ("No location or department is showing a renewal-threatening trend. "
                "Maintain current safety and engagement programs.")
    where = ", ".join(f"{d['dimension_type']} {d['dimension_value']}" for d in hot[:3])
    return (f"Deploy targeted stabilization at {where}: pair an EAP / mental-health push with "
            "a safety stand-down to protect the health-plan demographic before renewal. "
            "High turnover alongside rising incidents is the leading operational indicator of "
            "a claims surge — acting now improves the renewal negotiating position.")
