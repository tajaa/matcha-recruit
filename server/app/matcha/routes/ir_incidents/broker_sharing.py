"""Client-controlled sharing of an incident's defense file with a broker.

A broker's link to a company does not imply consent to the company's incident
narratives, witness names and corrective actions — so the broker-facing defense
endpoints (`routes/broker/submission.py`) serve only what a client has shared
here. This is the company side: list which of its brokers can see an incident,
and grant / revoke per broker.

Per broker, not per company: a client with two brokers can share a sensitive
incident with one and not the other. "Broker" means *currently linked* — the
same `ACTIVE_LINK_STATUSES` the broker↔company chat enforces — so a broker in
grace still resolves and a terminated one disappears from the picker (and, on
the read side, loses the shares it already had).

2+ segment paths so nothing collides with CRUD's `/{incident_id}`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.services import broker_chat_service as chat_svc

from ._shared import log_audit

router = APIRouter()


async def _assert_incident_in_company(conn, incident_id: UUID, company_id: UUID) -> None:
    """404 (not 403) on someone else's incident — an outsider learns nothing
    about whether the id exists."""
    owned = await conn.fetchval(
        "SELECT 1 FROM ir_incidents WHERE id = $1 AND company_id = $2",
        incident_id, company_id,
    )
    if not owned:
        raise HTTPException(status_code=404, detail="Incident not found")


async def _company_or_404(current_user) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return company_id


@router.get("/{incident_id}/broker-shares")
async def list_incident_broker_shares(
    incident_id: UUID, current_user=Depends(require_admin_or_client)
):
    """This incident's share state, one row per *currently linked* broker.

    Returns an empty list when the company has no broker — the UI renders
    nothing rather than an empty share control."""
    company_id = await _company_or_404(current_user)
    async with get_connection() as conn:
        await _assert_incident_in_company(conn, incident_id, company_id)
        broker_ids = await chat_svc.company_active_broker_ids(conn, company_id)
        if not broker_ids:
            return {"brokers": []}
        rows = await conn.fetch(
            """
            SELECT b.id, b.name, (s.id IS NOT NULL) AS shared, s.created_at AS shared_at
            FROM brokers b
            LEFT JOIN broker_incident_shares s
                   ON s.broker_id = b.id AND s.incident_id = $2
            WHERE b.id = ANY($1::uuid[])
            ORDER BY b.name
            """,
            broker_ids, incident_id,
        )
    return {
        "brokers": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "shared": r["shared"],
                "shared_at": r["shared_at"].isoformat() if r["shared_at"] else None,
            }
            for r in rows
        ]
    }


@router.put("/{incident_id}/broker-shares/{broker_id}")
async def share_incident_with_broker(
    incident_id: UUID, broker_id: UUID, current_user=Depends(require_admin_or_client)
):
    """Grant this broker access to the incident's defense file. Idempotent."""
    company_id = await _company_or_404(current_user)
    async with get_connection() as conn:
        await _assert_incident_in_company(conn, incident_id, company_id)
        if broker_id not in await chat_svc.company_active_broker_ids(conn, company_id):
            raise HTTPException(status_code=403, detail="Not linked to that broker")
        async with conn.transaction():
            # RETURNING distinguishes a real grant from a repeat click — logging
            # both would put a "granted" entry in the trail for a no-op.
            granted = await conn.fetchval(
                """
                INSERT INTO broker_incident_shares
                    (company_id, incident_id, broker_id, shared_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (incident_id, broker_id) DO NOTHING
                RETURNING id
                """,
                company_id, incident_id, broker_id, current_user.id,
            )
            if granted:
                await log_audit(conn, incident_id, current_user.id, "broker_share_granted",
                                entity_type="broker", entity_id=str(broker_id),
                                details={"broker_id": str(broker_id)})
    return {"shared": True}


@router.delete("/{incident_id}/broker-shares/{broker_id}", status_code=204)
async def unshare_incident_with_broker(
    incident_id: UUID, broker_id: UUID, current_user=Depends(require_admin_or_client)
):
    """Revoke. Deleting the row is the revocation — a share is present-tense
    state, and the audit log carries the history.

    Deliberately not gated on the broker still being linked: revoking access
    from a broker whose link has lapsed must stay possible."""
    company_id = await _company_or_404(current_user)
    async with get_connection() as conn:
        await _assert_incident_in_company(conn, incident_id, company_id)
        async with conn.transaction():
            deleted = await conn.execute(
                "DELETE FROM broker_incident_shares "
                "WHERE incident_id = $1 AND broker_id = $2 AND company_id = $3",
                incident_id, broker_id, company_id,
            )
            if deleted != "DELETE 0":
                await log_audit(conn, incident_id, current_user.id, "broker_share_revoked",
                                entity_type="broker", entity_id=str(broker_id),
                                details={"broker_id": str(broker_id)})
    return Response(status_code=204)
