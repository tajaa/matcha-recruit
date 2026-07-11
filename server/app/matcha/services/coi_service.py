"""Certificate-of-insurance tracking: persistence, verification, expiry status.

Verification reuses ``limit_adequacy.analyze`` — the certificate's carried limits
become the ``carried`` argument and the linked ``company_contracts`` row supplies
the required limits, so a COI is checked against exactly the contract that demanded
it. Expiry status drives the dashboard + the Celery sweep.
"""

import json
from datetime import date, timedelta
from uuid import UUID

from . import coi_parser, limit_adequacy as la

EXPIRING_WINDOW_DAYS = 30


def compute_status(expiry_date, today: date | None = None) -> str:
    """active | expiring (≤30d) | expired | unknown (no date)."""
    if not expiry_date:
        return "unknown"
    if isinstance(expiry_date, str):
        try:
            expiry_date = date.fromisoformat(expiry_date[:10])
        except ValueError:
            return "unknown"
    today = today or date.today()
    if expiry_date < today:
        return "expired"
    if expiry_date <= today + timedelta(days=EXPIRING_WINDOW_DAYS):
        return "expiring"
    return "active"


async def create_certificate(conn, company_id: UUID, parsed: dict, *,
                             holder_name: str | None, contract_id: UUID | None,
                             storage_path: str | None, source_filename: str | None,
                             uploaded_by: UUID | None) -> dict:
    """Persist a parsed certificate, then return the verified row."""
    lines = parsed.get("lines") or []
    expiry = coi_parser.earliest_expiry(lines)
    row = await conn.fetchrow(
        """
        INSERT INTO company_certificates
            (company_id, holder_name, carrier, certificate_number, lines, expiry_date,
             status, contract_id, source_filename, storage_path, ai_available, uploaded_by)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11, $12)
        RETURNING *
        """,
        company_id,
        holder_name or parsed.get("holder_name"),
        parsed.get("carrier"),
        parsed.get("certificate_number"),
        json.dumps(lines),
        expiry,
        compute_status(expiry),
        contract_id,
        source_filename,
        storage_path,
        bool(parsed.get("available")),
        uploaded_by,
    )
    return await _verify_and_serialize(conn, company_id, row)


async def list_certificates(conn, company_id: UUID) -> dict:
    """All certificates for a company + a status rollup."""
    rows = await conn.fetch(
        "SELECT * FROM company_certificates WHERE company_id = $1 ORDER BY expiry_date NULLS LAST",
        company_id,
    )
    certs = [await _verify_and_serialize(conn, company_id, r) for r in rows]
    summary = {"total": len(certs), "active": 0, "expiring": 0, "expired": 0, "unknown": 0,
               "with_gaps": 0}
    for c in certs:
        summary[c["status"]] = summary.get(c["status"], 0) + 1
        # verification is None when the cert isn't linked to a contract — guard
        # the chain (the key is present with value None, so .get() default won't help).
        vsummary = (c.get("verification") or {}).get("summary") or {}
        if vsummary.get("contract_shortfalls"):
            summary["with_gaps"] += 1
    return {"certificates": certs, "summary": summary}


async def delete_certificate(conn, company_id: UUID, cert_id: UUID) -> bool:
    result = await conn.execute(
        "DELETE FROM company_certificates WHERE id = $1 AND company_id = $2", cert_id, company_id,
    )
    return result != "DELETE 0"


async def _verify_and_serialize(conn, company_id: UUID, row) -> dict:
    """Row → dict with recomputed status + a limit-adequacy verification vs. the
    linked contract's required limits (if any)."""
    lines = row["lines"]
    if isinstance(lines, str):
        lines = json.loads(lines)
    carried = [{"line": ln["line"], "per_occurrence": ln.get("per_occurrence"),
                "aggregate": ln.get("aggregate"), "carrier": row["carrier"],
                "expiry_date": ln.get("expiry_date"),
                "additional_insured": ln.get("additional_insured"),
                "waiver_of_subrogation": ln.get("waiver_of_subrogation")}
               for ln in (lines or [])]

    contracts: list[dict] = []
    if row["contract_id"]:
        c = await conn.fetchrow(
            "SELECT id, name, counterparty, requirements FROM company_contracts WHERE id = $1 AND company_id = $2",
            row["contract_id"], company_id,
        )
        if c:
            reqs = c["requirements"]
            if isinstance(reqs, str):
                reqs = json.loads(reqs)
            contracts = [{"id": str(c["id"]), "name": c["name"], "counterparty": c["counterparty"],
                          "requirements": reqs or []}]

    verification = None
    if contracts:
        try:
            verification = la.analyze(carried, contracts, headcount=None, venue_tier=None)
        except Exception:
            verification = None

    return {
        "id": str(row["id"]),
        "holder_name": row["holder_name"],
        "carrier": row["carrier"],
        "certificate_number": row["certificate_number"],
        "lines": lines or [],
        "expiry_date": row["expiry_date"].isoformat() if row["expiry_date"] else None,
        "status": compute_status(row["expiry_date"]),
        "contract_id": str(row["contract_id"]) if row["contract_id"] else None,
        "ai_available": row["ai_available"],
        "source_filename": row["source_filename"],
        "verification": verification,
    }
