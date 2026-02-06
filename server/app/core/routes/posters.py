"""Client-facing compliance poster routes."""

import logging
from io import BytesIO
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ...database import get_connection
from ...matcha.dependencies import require_admin_or_client, get_client_company_id
from ..models.posters import PosterOrderCreate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/available")
async def get_available_posters(
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Get available posters for the company's locations."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                bl.id AS location_id,
                bl.name AS location_name,
                bl.city AS location_city,
                bl.state AS location_state,
                bl.jurisdiction_id,
                pt.id AS template_id,
                pt.title AS template_title,
                pt.status AS template_status,
                pt.version AS template_version,
                pt.pdf_url,
                pt.pdf_generated_at,
                pt.categories_included,
                EXISTS(
                    SELECT 1 FROM poster_orders po
                    WHERE po.location_id = bl.id
                      AND po.status NOT IN ('cancelled', 'delivered')
                ) AS has_active_order
            FROM business_locations bl
            LEFT JOIN poster_templates pt ON bl.jurisdiction_id = pt.jurisdiction_id
            WHERE bl.company_id = $1 AND bl.is_active = true
            ORDER BY bl.state, bl.city
            """,
            company_id,
        )

        posters = []
        for r in rows:
            posters.append({
                "location_id": str(r["location_id"]),
                "location_name": r["location_name"],
                "location_city": r["location_city"],
                "location_state": r["location_state"],
                "jurisdiction_id": str(r["jurisdiction_id"]) if r["jurisdiction_id"] else None,
                "template_id": str(r["template_id"]) if r["template_id"] else None,
                "template_title": r["template_title"],
                "template_status": r["template_status"],
                "template_version": r["template_version"],
                "pdf_url": r["pdf_url"],
                "pdf_generated_at": r["pdf_generated_at"].isoformat() if r["pdf_generated_at"] else None,
                "categories_included": r["categories_included"],
                "has_active_order": r["has_active_order"],
            })
        return posters


@router.post("/orders")
async def create_poster_order(
    order: PosterOrderCreate,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Place a poster order for a company location."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated")

    async with get_connection() as conn:
        # Verify location belongs to company
        loc = await conn.fetchrow(
            "SELECT id, city, state FROM business_locations WHERE id = $1 AND company_id = $2 AND is_active = true",
            order.location_id, company_id,
        )
        if not loc:
            raise HTTPException(status_code=404, detail="Location not found or not owned by your company")

        # Verify all templates exist and are generated
        for tid in order.template_ids:
            tpl = await conn.fetchrow(
                "SELECT id, status FROM poster_templates WHERE id = $1",
                tid,
            )
            if not tpl:
                raise HTTPException(status_code=404, detail=f"Template {tid} not found")
            if tpl["status"] != "generated":
                raise HTTPException(status_code=400, detail=f"Template {tid} does not have a generated poster")

        # Build shipping address from location if not provided
        shipping = order.shipping_address
        if not shipping:
            shipping = f"{loc['city']}, {loc['state']}"

        # Create order
        order_row = await conn.fetchrow(
            """
            INSERT INTO poster_orders (company_id, location_id, requested_by, shipping_address)
            VALUES ($1, $2, $3, $4)
            RETURNING id, created_at
            """,
            company_id, order.location_id, current_user.id, shipping,
        )

        # Create order items
        for tid in order.template_ids:
            await conn.execute(
                """
                INSERT INTO poster_order_items (order_id, template_id, quantity)
                VALUES ($1, $2, $3)
                """,
                order_row["id"], tid, order.quantity,
            )

        return {
            "id": str(order_row["id"]),
            "status": "requested",
            "created_at": order_row["created_at"].isoformat(),
            "message": "Poster order placed successfully",
        }


@router.get("/orders")
async def list_company_poster_orders(
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Get the company's poster order history."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT po.*,
                   bl.name AS location_name, bl.city AS location_city, bl.state AS location_state
            FROM poster_orders po
            JOIN business_locations bl ON po.location_id = bl.id
            WHERE po.company_id = $1
            ORDER BY po.created_at DESC
            """,
            company_id,
        )

        orders = []
        for r in rows:
            items = await conn.fetch(
                """
                SELECT poi.*, pt.title AS template_title,
                       j.city || ', ' || j.state AS jurisdiction_name
                FROM poster_order_items poi
                JOIN poster_templates pt ON poi.template_id = pt.id
                JOIN jurisdictions j ON pt.jurisdiction_id = j.id
                WHERE poi.order_id = $1
                """,
                r["id"],
            )
            orders.append({
                "id": str(r["id"]),
                "company_id": str(r["company_id"]),
                "location_id": str(r["location_id"]),
                "status": r["status"],
                "admin_notes": r["admin_notes"],
                "quote_amount": float(r["quote_amount"]) if r["quote_amount"] else None,
                "shipping_address": r["shipping_address"],
                "tracking_number": r["tracking_number"],
                "shipped_at": r["shipped_at"].isoformat() if r["shipped_at"] else None,
                "delivered_at": r["delivered_at"].isoformat() if r["delivered_at"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                "location_name": r["location_name"],
                "location_city": r["location_city"],
                "location_state": r["location_state"],
                "items": [
                    {
                        "id": str(i["id"]),
                        "template_id": str(i["template_id"]),
                        "quantity": i["quantity"],
                        "template_title": i["template_title"],
                        "jurisdiction_name": i["jurisdiction_name"],
                    }
                    for i in items
                ],
            })
        return {"orders": orders, "total": len(orders)}


@router.get("/orders/{order_id}")
async def get_company_poster_order(
    order_id: UUID,
    current_user=Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Get a specific poster order detail (scoped to company)."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated")

    async with get_connection() as conn:
        r = await conn.fetchrow(
            """
            SELECT po.*,
                   bl.name AS location_name, bl.city AS location_city, bl.state AS location_state
            FROM poster_orders po
            JOIN business_locations bl ON po.location_id = bl.id
            WHERE po.id = $1 AND po.company_id = $2
            """,
            order_id, company_id,
        )
        if not r:
            raise HTTPException(status_code=404, detail="Order not found")

        items = await conn.fetch(
            """
            SELECT poi.*, pt.title AS template_title,
                   j.city || ', ' || j.state AS jurisdiction_name
            FROM poster_order_items poi
            JOIN poster_templates pt ON poi.template_id = pt.id
            JOIN jurisdictions j ON pt.jurisdiction_id = j.id
            WHERE poi.order_id = $1
            """,
            order_id,
        )
        return {
            "id": str(r["id"]),
            "company_id": str(r["company_id"]),
            "location_id": str(r["location_id"]),
            "status": r["status"],
            "admin_notes": r["admin_notes"],
            "quote_amount": float(r["quote_amount"]) if r["quote_amount"] else None,
            "shipping_address": r["shipping_address"],
            "tracking_number": r["tracking_number"],
            "shipped_at": r["shipped_at"].isoformat() if r["shipped_at"] else None,
            "delivered_at": r["delivered_at"].isoformat() if r["delivered_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            "location_name": r["location_name"],
            "location_city": r["location_city"],
            "location_state": r["location_state"],
            "items": [
                {
                    "id": str(i["id"]),
                    "template_id": str(i["template_id"]),
                    "quantity": i["quantity"],
                    "template_title": i["template_title"],
                    "jurisdiction_name": i["jurisdiction_name"],
                }
                for i in items
            ],
        }


@router.get("/preview/{template_id}")
async def preview_poster_pdf(
    template_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Download/preview a poster PDF by template ID."""
    async with get_connection() as conn:
        tpl = await conn.fetchrow(
            "SELECT pdf_url, title, status FROM poster_templates WHERE id = $1",
            template_id,
        )
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        if tpl["status"] != "generated" or not tpl["pdf_url"]:
            raise HTTPException(status_code=400, detail="Poster PDF not available")

        # Return the PDF URL for client to download
        return {"pdf_url": tpl["pdf_url"], "title": tpl["title"]}
