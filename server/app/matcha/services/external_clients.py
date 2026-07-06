"""Off-platform broker clients (Broker Pro).

Clients a broker manages who are **not** Matcha tenants. There's no operational
data to derive from, so the broker keys in a WC loss-run summary + an EPL
questionnaire; the same scoring engines run on those inputs:

- WC  → reuse ``wc_benchmarks`` (TRIR/DART, benchmark, severity band, premium)
        + ``wc_depth`` NCCI state-rate overlay, computed from broker-entered counts.
- EPL → reuse ``epl_readiness.assess_from_statuses`` (same factors/weights/bands;
        every factor is broker-attested here).

Scores stay directly comparable to on-platform (pass-through) clients. Caller
owns the asyncpg connection; all reads are broker-scoped by broker_id.
"""

import secrets
from typing import Optional
from uuid import UUID

from . import wc_depth
from . import epl_readiness
from . import risk_index
from . import loss_development
from .wc_benchmarks import lookup_benchmark, estimate_premium_impact, severity_band


# --- identity --------------------------------------------------------------

def _serialize_client(r) -> dict:
    return {
        "id": str(r["id"]),
        "broker_id": str(r["broker_id"]),
        "name": r["name"],
        "industry": r["industry"],
        "headcount": r["headcount"],
        "primary_state": r["primary_state"],
        "note": r["note"],
        "status": r["status"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


async def list_clients(conn, broker_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, broker_id, name, industry, headcount, primary_state, note, status, created_at
        FROM broker_external_clients
        WHERE broker_id = $1 AND status = 'active'
        ORDER BY name
        """,
        broker_id,
    )
    return [_serialize_client(r) for r in rows]


async def get_client(conn, broker_id: UUID, client_id: UUID) -> Optional[dict]:
    r = await conn.fetchrow(
        """
        SELECT id, broker_id, name, industry, headcount, primary_state, note, status, created_at
        FROM broker_external_clients WHERE id = $1 AND broker_id = $2
        """,
        client_id, broker_id,
    )
    return _serialize_client(r) if r else None


async def create_client(conn, broker_id, created_by, *, name, industry, headcount,
                        primary_state, note) -> dict:
    r = await conn.fetchrow(
        """
        INSERT INTO broker_external_clients (broker_id, name, industry, headcount, primary_state, note, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, broker_id, name, industry, headcount, primary_state, note, status, created_at
        """,
        broker_id, name, industry, headcount,
        (primary_state or "").upper()[:2] or None, note, created_by,
    )
    return _serialize_client(r)


async def update_client(conn, broker_id, client_id, *, name, industry, headcount,
                        primary_state, note) -> Optional[dict]:
    r = await conn.fetchrow(
        """
        UPDATE broker_external_clients
        SET name = $3, industry = $4, headcount = $5, primary_state = $6, note = $7, updated_at = NOW()
        WHERE id = $1 AND broker_id = $2
        RETURNING id, broker_id, name, industry, headcount, primary_state, note, status, created_at
        """,
        client_id, broker_id, name, industry, headcount,
        (primary_state or "").upper()[:2] or None, note,
    )
    return _serialize_client(r) if r else None


async def archive_client(conn, broker_id, client_id) -> bool:
    result = await conn.execute(
        "UPDATE broker_external_clients SET status = 'archived', updated_at = NOW() WHERE id = $1 AND broker_id = $2",
        client_id, broker_id,
    )
    return result.split()[-1] != "0"


# --- WC snapshot -----------------------------------------------------------

async def upsert_wc_snapshot(conn, client_id: UUID, updated_by, data: dict) -> None:
    await conn.execute(
        """
        INSERT INTO broker_external_wc
            (external_client_id, period_label, recordable_cases, dart_cases, lost_days, restricted_days,
             ct_cases, acute_cases, post_termination_cases, lost_time_open, lost_time_resolved,
             avg_days_to_rtw, current_emr, carrier, annual_premium, updated_by, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16, NOW())
        ON CONFLICT (external_client_id) DO UPDATE SET
            period_label=EXCLUDED.period_label, recordable_cases=EXCLUDED.recordable_cases,
            dart_cases=EXCLUDED.dart_cases, lost_days=EXCLUDED.lost_days, restricted_days=EXCLUDED.restricted_days,
            ct_cases=EXCLUDED.ct_cases, acute_cases=EXCLUDED.acute_cases,
            post_termination_cases=EXCLUDED.post_termination_cases, lost_time_open=EXCLUDED.lost_time_open,
            lost_time_resolved=EXCLUDED.lost_time_resolved, avg_days_to_rtw=EXCLUDED.avg_days_to_rtw,
            current_emr=EXCLUDED.current_emr, carrier=EXCLUDED.carrier, annual_premium=EXCLUDED.annual_premium,
            updated_by=EXCLUDED.updated_by, updated_at=NOW()
        """,
        client_id, data.get("period_label"), data.get("recordable_cases", 0), data.get("dart_cases", 0),
        data.get("lost_days", 0), data.get("restricted_days", 0), data.get("ct_cases", 0),
        data.get("acute_cases", 0), data.get("post_termination_cases", 0), data.get("lost_time_open", 0),
        data.get("lost_time_resolved", 0), data.get("avg_days_to_rtw"), data.get("current_emr"),
        data.get("carrier"), data.get("annual_premium"), updated_by,
    )


def _compute_wc(client: dict, snap, state_rate) -> dict:
    """WC metrics from the broker-entered snapshot, via the shared benchmarks."""
    headcount = client.get("headcount") or 0
    rec = int(snap["recordable_cases"]) if snap else 0
    dart = int(snap["dart_cases"]) if snap else 0
    lost = int(snap["lost_days"]) if snap else 0
    hours = headcount * 2000.0 if headcount > 0 else 0.0
    trir = round(rec * 200_000 / hours, 2) if hours > 0 else None
    dart_rate = round(dart * 200_000 / hours, 2) if hours > 0 else None
    bench = lookup_benchmark(client.get("industry"))
    bench_trir = bench["trir"] if bench else None
    ct = int(snap["ct_cases"]) if snap else 0
    acute = int(snap["acute_cases"]) if snap else 0
    return {
        "has_data": snap is not None,
        "period_label": snap["period_label"] if snap else None,
        "headcount": headcount or None,
        "recordable_cases": rec,
        "dart_cases": dart,
        "lost_days": lost,
        "trir": trir,
        "dart_rate": dart_rate,
        "benchmark": bench,
        "severity_band": severity_band(trir, bench_trir),
        "premium_impact": estimate_premium_impact(
            trir=trir, benchmark_trir=bench_trir,
            headcount=headcount or None, sector=bench["sector"] if bench else None,
        ),
        "claim_breakdown": {
            "cumulative_trauma": ct,
            "acute": acute,
            "unknown": max(rec - ct - acute, 0),
        },
        "post_termination_cases": int(snap["post_termination_cases"]) if snap else 0,
        "rtw": {
            "open": int(snap["lost_time_open"]) if snap else 0,
            "resolved": int(snap["lost_time_resolved"]) if snap else 0,
            "avg_days_to_rtw": float(snap["avg_days_to_rtw"]) if snap and snap["avg_days_to_rtw"] is not None else None,
        },
        "current_emr": float(snap["current_emr"]) if snap and snap["current_emr"] is not None else None,
        "carrier": snap["carrier"] if snap else None,
        "annual_premium": float(snap["annual_premium"]) if snap and snap["annual_premium"] is not None else None,
        "state_rate": state_rate,
    }


# --- EPL attestations ------------------------------------------------------

async def upsert_epl_attestation(conn, client_id: UUID, item_key: str, status: str,
                                 note, updated_by) -> None:
    await conn.execute(
        """
        INSERT INTO broker_external_epl_attestations (external_client_id, item_key, status, note, updated_by, updated_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT ON CONSTRAINT uq_broker_external_epl DO UPDATE SET
            status = EXCLUDED.status, note = EXCLUDED.note, updated_by = EXCLUDED.updated_by, updated_at = NOW()
        """,
        client_id, item_key, status, note, updated_by,
    )


async def _epl_for_client(conn, client_id: UUID) -> dict:
    rows = await conn.fetch(
        "SELECT item_key, status, note FROM broker_external_epl_attestations WHERE external_client_id = $1",
        client_id,
    )
    by_key = {r["item_key"]: r for r in rows}
    assessment = epl_readiness.assess_from_statuses({k: v["status"] for k, v in by_key.items()})
    # overlay broker notes onto the factor list
    for f in assessment["factors"]:
        row = by_key.get(f["key"])
        f["note"] = row["note"] if row else None
    return assessment


# --- property snapshot (broker-keyed summary; mirror of broker_external_wc) ----

async def upsert_property_snapshot(conn, client_id: UUID, updated_by, data: dict) -> None:
    await conn.execute(
        """
        INSERT INTO broker_external_property
            (external_client_id, period_label, building_count, total_tiv, worst_construction,
             sprinklered_pct, worst_cat_tier, insured_to_value_pct, carrier, annual_premium, note,
             updated_by, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, NOW())
        ON CONFLICT (external_client_id) DO UPDATE SET
            period_label=EXCLUDED.period_label, building_count=EXCLUDED.building_count,
            total_tiv=EXCLUDED.total_tiv, worst_construction=EXCLUDED.worst_construction,
            sprinklered_pct=EXCLUDED.sprinklered_pct, worst_cat_tier=EXCLUDED.worst_cat_tier,
            insured_to_value_pct=EXCLUDED.insured_to_value_pct, carrier=EXCLUDED.carrier,
            annual_premium=EXCLUDED.annual_premium, note=EXCLUDED.note,
            updated_by=EXCLUDED.updated_by, updated_at=NOW()
        """,
        client_id, data.get("period_label"), data.get("building_count", 0), data.get("total_tiv"),
        data.get("worst_construction"), data.get("sprinklered_pct"), data.get("worst_cat_tier"),
        data.get("insured_to_value_pct"), data.get("carrier"), data.get("annual_premium"),
        data.get("note"), updated_by,
    )


async def _property_snap(conn, client_id: UUID):
    """Fetch the broker-keyed property snapshot. Best-effort: returns None if the
    table isn't present yet (code deployed before prop01) so the pre-existing
    external-client + risk-curve endpoints don't 500 on migration lag."""
    import asyncpg
    try:
        return await conn.fetchrow(
            "SELECT * FROM broker_external_property WHERE external_client_id = $1", client_id)
    except asyncpg.exceptions.UndefinedTableError:
        return None


def _compute_property(snap) -> dict:
    """Property metrics from the broker-entered summary snapshot. Builds a synthetic
    rollup (coarse COPE from construction + sprinkler%, ITV from insured-to-value%)
    so the shared ``risk_index.external_risk_index`` property component can score it."""
    if not snap:
        return {"has_data": False, "building_count": 0, "total_tiv": None,
                "worst_construction": None, "sprinklered_pct": None, "worst_cat_tier": None,
                "insured_to_value_pct": None, "carrier": None, "annual_premium": None,
                "rollup": {"building_count": 0}, "cat": None}
    from . import property_sov
    bc = int(snap["building_count"] or 0)
    cope_base = property_sov.CONSTRUCTION_GRADE.get((snap["worst_construction"] or "").strip().lower(), 50)
    spr = int(snap["sprinklered_pct"]) if snap["sprinklered_pct"] is not None else 0
    cope_score = round(min(100, max(0, cope_base * 0.7 + spr * 0.3)))
    itv_pct = snap["insured_to_value_pct"]
    ratio = (itv_pct / 100.0) if itv_pct is not None else None
    rollup = {
        "building_count": bc,
        "avg_cope_score": cope_score if bc else None,
        "itv": {"portfolio_ratio": ratio, "under_count": 1 if (ratio is not None and ratio < 0.90) else 0,
                "rated_count": bc},
    }
    cat = {"worst_tier": snap["worst_cat_tier"]} if snap["worst_cat_tier"] else None
    return {
        "has_data": True, "building_count": bc,
        "total_tiv": float(snap["total_tiv"]) if snap["total_tiv"] is not None else None,
        "worst_construction": snap["worst_construction"], "sprinklered_pct": spr,
        "worst_cat_tier": snap["worst_cat_tier"], "insured_to_value_pct": itv_pct,
        "carrier": snap["carrier"],
        "annual_premium": float(snap["annual_premium"]) if snap["annual_premium"] is not None else None,
        "period_label": snap["period_label"], "cope_score": cope_score,
        "rollup": rollup, "cat": cat,
    }


# --- assembled views -------------------------------------------------------

async def _wc_reserve_confidence(conn, broker_id: UUID, client_id: UUID) -> str:
    """Reserve confidence of this external client's WC loss-run triangle, folded
    into the composite so a volatile/thin triangle doesn't read high-confidence.
    "high" when there are no WC loss runs (no volatility signal). Never raises."""
    try:
        tri = await loss_development.build_development(conn, broker_id, "external", client_id)
        wc_line = next((ln for ln in tri["lines"] if ln["line"] == "wc"), None)
        return wc_line["summary"]["reserve_confidence"] if wc_line else "high"
    except Exception:
        return "high"


async def client_detail(conn, broker_id: UUID, client_id: UUID) -> Optional[dict]:
    client = await get_client(conn, broker_id, client_id)
    if not client:
        return None
    snap = await conn.fetchrow("SELECT * FROM broker_external_wc WHERE external_client_id = $1", client_id)
    state = client.get("primary_state")
    rates = await wc_depth.get_state_rates(conn, [state]) if state else {}
    wc = _compute_wc(client, snap, rates.get(state) if state else None)
    wc["reserve_confidence"] = await _wc_reserve_confidence(conn, broker_id, client_id)
    epl = await _epl_for_client(conn, client_id)
    prop = _compute_property(await _property_snap(conn, client_id))
    intake = await intake_status(conn, client_id)
    return {"client": client, "wc": wc, "epl": epl, "property": prop,
            "risk_index": risk_index.external_risk_index(wc, epl, prop), "intake": intake}


async def list_with_scores(conn, broker_id: UUID) -> list[dict]:
    """List view: identity + WC band + EPL score/band + property per external client."""
    clients = await list_clients(conn, broker_id)
    intakes = await intake_status_map(conn, [UUID(c["id"]) for c in clients])
    out = []
    for c in clients:
        cid = UUID(c["id"])
        snap = await conn.fetchrow("SELECT * FROM broker_external_wc WHERE external_client_id = $1", cid)
        wc = _compute_wc(c, snap, None)
        wc["reserve_confidence"] = await _wc_reserve_confidence(conn, broker_id, cid)
        epl = await _epl_for_client(conn, cid)
        prop = _compute_property(await _property_snap(conn, cid))
        ri = risk_index.external_risk_index(wc, epl, prop)
        intake = intakes.get(c["id"], {"status": "not_sent", "is_submitted": False, "submitted_at": None})
        out.append({
            **c,
            "wc_severity_band": wc["severity_band"],
            "wc_trir": wc["trir"],
            "wc_current_emr": wc["current_emr"],
            "annual_premium": wc["annual_premium"],
            "epl_score": epl["score"],
            "epl_band": epl["band"],
            "property_building_count": prop["building_count"],
            "property_tiv": prop["total_tiv"],
            "property_cat_tier": prop["worst_cat_tier"],
            "risk_index": ri["index"],
            "risk_band": ri["band"],
            "risk_confidence": ri.get("index_confidence"),
            "intake_status": intake["status"],
            "intake_submitted_at": intake["submitted_at"],
        })
    return out


# --- client-intake links (extintake01) -------------------------------------

INTAKE_TTL_DAYS = 14
_EPL_STATUSES = {"in_place", "partial", "gap", "unknown"}


async def create_intake_token(conn, broker_id: UUID, client_id: UUID, created_by,
                              ttl_days: int = INTAKE_TTL_DAYS) -> Optional[dict]:
    """Mint a shareable intake token for an owned external client. None if not owned."""
    if not await get_client(conn, broker_id, client_id):
        return None
    token = secrets.token_urlsafe(24)
    row = await conn.fetchrow(
        """
        INSERT INTO broker_external_intake_tokens
            (token, external_client_id, broker_id, created_by, expires_at)
        VALUES ($1, $2, $3, $4, NOW() + make_interval(days => $5))
        RETURNING token, expires_at
        """,
        token, client_id, broker_id, created_by, ttl_days,
    )
    return {"token": row["token"], "expires_at": row["expires_at"]}


async def get_intake(conn, token: str) -> Optional[dict]:
    """Token row + client name + is_open (active & unexpired). None if no such token."""
    row = await conn.fetchrow(
        """
        SELECT t.id, t.external_client_id, t.broker_id, t.created_by, t.status,
               t.expires_at, t.completed_at, c.name AS client_name, c.industry,
               (t.status = 'active' AND t.expires_at > NOW()) AS is_open
        FROM broker_external_intake_tokens t
        JOIN broker_external_clients c ON c.id = t.external_client_id
        WHERE t.token = $1
        """,
        token,
    )
    return dict(row) if row else None


def intake_factors() -> list[dict]:
    """The questionnaire shown to the prospect — every EPL factor, self-attested."""
    return [{"key": f["key"], "label": f["label"]} for f in epl_readiness.FACTORS]


async def complete_intake(conn, token_row: dict, epl: dict, wc: Optional[dict]) -> None:
    """Persist the prospect's answers, attributed to the broker who sent the link,
    then lock the token + stamp the completion time (the submission timestamp the
    broker reads back to confirm the EPL data is current)."""
    cid = token_row["external_client_id"]
    by = token_row["created_by"]
    valid_keys = {f["key"] for f in epl_readiness.FACTORS}
    for key, status in (epl or {}).items():
        if key in valid_keys and status in _EPL_STATUSES:
            await upsert_epl_attestation(conn, cid, key, status, None, by)
    if wc:
        await upsert_wc_snapshot(conn, cid, by, wc)
    await conn.execute(
        "UPDATE broker_external_intake_tokens SET status = 'completed', completed_at = NOW() WHERE id = $1",
        token_row["id"],
    )


# --- intake submission status (derived from the token ledger; no extra column) ---

def _intake_state(submitted_at, pending_at) -> str:
    """Classify a client's intake state from the token ledger. Pure (unit-tested).

    'submitted' = the client self-completed a link at least once; 'pending' = a
    live (active, unexpired) link is outstanding and awaiting the client; 'not_sent'
    = no link minted yet. A past submission outranks a newer pending link so the
    broker always sees that current answers exist."""
    if submitted_at:
        return "submitted"
    if pending_at:
        return "pending"
    return "not_sent"


def _intake_payload(submitted_at, pending_at, pending_expires_at) -> dict:
    return {
        "status": _intake_state(submitted_at, pending_at),
        "is_submitted": submitted_at is not None,
        "submitted_at": submitted_at.isoformat() if submitted_at else None,
        "pending_sent_at": pending_at.isoformat() if pending_at else None,
        "pending_expires_at": pending_expires_at.isoformat() if pending_expires_at else None,
    }


async def intake_status(conn, client_id: UUID) -> dict:
    """One client's intake submission state, derived from its intake tokens.

    ``submitted_at`` is the most recent client self-completion (``completed_at`` on
    a completed token) — the timestamp the broker reads to verify the EPL answers
    are current. No schema change: the token table already records all of it."""
    row = await conn.fetchrow(
        """
        SELECT
            MAX(completed_at) FILTER (WHERE status = 'completed')                       AS submitted_at,
            MAX(created_at)   FILTER (WHERE status = 'active' AND expires_at > NOW())    AS pending_at,
            MAX(expires_at)   FILTER (WHERE status = 'active' AND expires_at > NOW())    AS pending_expires_at
        FROM broker_external_intake_tokens
        WHERE external_client_id = $1
        """,
        client_id,
    )
    return _intake_payload(
        row["submitted_at"] if row else None,
        row["pending_at"] if row else None,
        row["pending_expires_at"] if row else None,
    )


async def intake_status_map(conn, client_ids) -> dict[str, dict]:
    """Batched ``intake_status`` for a roster → {client_id_str: payload}. One query
    over the whole book for the list/dashboard rollup."""
    ids = list({c for c in client_ids})
    if not ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT external_client_id,
            MAX(completed_at) FILTER (WHERE status = 'completed')                    AS submitted_at,
            MAX(created_at)   FILTER (WHERE status = 'active' AND expires_at > NOW()) AS pending_at,
            MAX(expires_at)   FILTER (WHERE status = 'active' AND expires_at > NOW()) AS pending_expires_at
        FROM broker_external_intake_tokens
        WHERE external_client_id = ANY($1::uuid[])
        GROUP BY external_client_id
        """,
        ids,
    )
    return {
        str(r["external_client_id"]): _intake_payload(
            r["submitted_at"], r["pending_at"], r["pending_expires_at"]
        )
        for r in rows
    }
