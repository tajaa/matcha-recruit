"""Master-admin product builder — compose sellable packages from feature flags.

Each row here is a product the admin assembled: a feature set, a paid gate, a
pricing model, and an optional nav ordering. Publishing one yields a shareable
/p/<slug>/signup URL; tenants who sign up get signup_source = 'product:<slug>'.

Every mutation snapshots the previous row into product_definition_history in
the same transaction — these fields set what customers are charged (same rule
as matcha_lite_pricing_admin.py).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.services.product_definitions import (
    ALLOWED_PRODUCT_FEATURES,
    PAID_PRICING_MODELS,
    PRICING_MODELS,
    SELECT_COLUMNS,
    SIGNUP_SOURCE_PREFIX,
    ProductDefinition,
    ProductDefinitionError,
    is_tenant_activated,
    materialize_features,
    row_to_product,
    validate_features,
    validate_gate_feature,
    validate_nav,
    validate_pricing,
    validate_slug,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class NavEntry(BaseModel):
    feature: str
    label: Optional[str] = None


class ProductUpsert(BaseModel):
    slug: str
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    features: dict[str, bool]
    gate_feature: Optional[str] = None
    pricing_model: str
    price_cents: Optional[int] = None
    block_size: Optional[int] = None
    min_headcount: int = 1
    max_headcount: int = 300
    nav: Optional[list[NavEntry]] = None


def _validated(body: ProductUpsert) -> dict[str, Any]:
    """Run every product invariant, returning the row payload to write."""
    try:
        slug = validate_slug(body.slug)
        features = validate_features(body.features)
        validate_pricing(
            body.pricing_model,
            body.price_cents,
            body.block_size,
            body.min_headcount,
            body.max_headcount,
        )
        gate = validate_gate_feature(body.gate_feature, features, body.pricing_model)
        nav = validate_nav(
            [e.model_dump() for e in body.nav] if body.nav is not None else None,
            features,
        )
    except ProductDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "slug": slug,
        "name": body.name.strip(),
        "description": (body.description or "").strip(),
        "features": json.dumps(features),
        "gate_feature": gate,
        "pricing_model": body.pricing_model,
        "price_cents": body.price_cents if body.pricing_model in PAID_PRICING_MODELS else None,
        "block_size": body.block_size if body.pricing_model == "block" else None,
        "min_headcount": body.min_headcount,
        "max_headcount": body.max_headcount,
        "nav": json.dumps(nav) if nav is not None else None,
    }


async def _snapshot(conn, product_id: UUID, changed_by: Optional[str]) -> None:
    """Record the CURRENT row before it is overwritten/archived."""
    row = await conn.fetchrow(
        f"SELECT {SELECT_COLUMNS} FROM product_definitions WHERE id = $1", product_id
    )
    if not row:
        return
    await conn.execute(
        """INSERT INTO product_definition_history (product_id, snapshot, changed_by)
           VALUES ($1, $2::jsonb, $3)""",
        product_id,
        json.dumps(row_to_product(row).to_dict()),
        changed_by,
    )


async def _tenant_counts(conn, products: list[ProductDefinition]) -> dict[str, dict]:
    """Per-product tenant counts: total signups vs activated (gate flag on)."""
    if not products:
        return {}
    sources = [p.signup_source for p in products]
    rows = await conn.fetch(
        """SELECT signup_source, enabled_features
             FROM companies
            WHERE signup_source = ANY($1::text[])""",
        sources,
    )
    by_slug = {p.signup_source: p for p in products}
    counts: dict[str, dict] = {p.slug: {"total": 0, "active": 0} for p in products}
    for row in rows:
        product = by_slug.get(row["signup_source"])
        if not product:
            continue
        entry = counts[product.slug]
        entry["total"] += 1
        if is_tenant_activated(product, row["enabled_features"]):
            entry["active"] += 1
    return counts


@router.get("/products")
async def list_products(current_user=Depends(require_admin)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT {SELECT_COLUMNS} FROM product_definitions ORDER BY created_at DESC"
        )
        products = [row_to_product(r) for r in rows]
        counts = await _tenant_counts(conn, products)
    return {
        "products": [{**p.to_dict(), "tenants": counts.get(p.slug, {"total": 0, "active": 0})} for p in products],
        # The builder's feature picker + gate select are driven by this list, so
        # a flag added to DEFAULT_COMPANY_FEATURES is sellable without a
        # frontend change.
        "available_features": sorted(ALLOWED_PRODUCT_FEATURES),
        "pricing_models": list(PRICING_MODELS),
    }


@router.post("/products", status_code=201)
async def create_product(body: ProductUpsert, current_user=Depends(require_admin)):
    payload = _validated(body)
    async with get_connection() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM product_definitions WHERE slug = $1", payload["slug"]
        )
        if exists:
            raise HTTPException(status_code=409, detail=f"Slug '{payload['slug']}' already exists")
        row = await conn.fetchrow(
            f"""INSERT INTO product_definitions
                    (slug, name, description, features, gate_feature, pricing_model,
                     price_cents, block_size, min_headcount, max_headcount, nav, updated_by)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10, $11::jsonb, $12)
                RETURNING {SELECT_COLUMNS}""",
            payload["slug"], payload["name"], payload["description"], payload["features"],
            payload["gate_feature"], payload["pricing_model"], payload["price_cents"],
            payload["block_size"], payload["min_headcount"], payload["max_headcount"],
            payload["nav"], current_user.email,
        )
    logger.info("Admin created product %s by %s", payload["slug"], current_user.email)
    return row_to_product(row).to_dict()


@router.put("/products/{product_id}")
async def update_product(
    product_id: UUID, body: ProductUpsert, current_user=Depends(require_admin)
):
    payload = _validated(body)
    async with get_connection() as conn:
        async with conn.transaction():
            current = await conn.fetchrow(
                "SELECT slug, status FROM product_definitions WHERE id = $1", product_id
            )
            if not current:
                raise HTTPException(status_code=404, detail="Product not found")
            if current["slug"] != payload["slug"]:
                # The slug is the signup URL and lives in every tenant's
                # signup_source — renaming would orphan them.
                clash = await conn.fetchval(
                    "SELECT 1 FROM product_definitions WHERE slug = $1 AND id <> $2",
                    payload["slug"], product_id,
                )
                if clash:
                    raise HTTPException(status_code=409, detail=f"Slug '{payload['slug']}' already exists")
                tenants = await conn.fetchval(
                    "SELECT COUNT(*) FROM companies WHERE signup_source = $1",
                    SIGNUP_SOURCE_PREFIX + current["slug"],
                )
                if tenants:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot rename the slug — {tenants} company(ies) already signed up on '{current['slug']}'",
                    )
            await _snapshot(conn, product_id, current_user.email)
            row = await conn.fetchrow(
                f"""UPDATE product_definitions
                       SET slug = $1, name = $2, description = $3, features = $4::jsonb,
                           gate_feature = $5, pricing_model = $6, price_cents = $7,
                           block_size = $8, min_headcount = $9, max_headcount = $10,
                           nav = $11::jsonb, updated_at = NOW(), updated_by = $12
                     WHERE id = $13
                 RETURNING {SELECT_COLUMNS}""",
                payload["slug"], payload["name"], payload["description"], payload["features"],
                payload["gate_feature"], payload["pricing_model"], payload["price_cents"],
                payload["block_size"], payload["min_headcount"], payload["max_headcount"],
                payload["nav"], current_user.email, product_id,
            )
    logger.info("Admin updated product %s by %s", payload["slug"], current_user.email)
    return row_to_product(row).to_dict()


class StatusChange(BaseModel):
    status: str


@router.post("/products/{product_id}/status")
async def set_product_status(
    product_id: UUID, body: StatusChange, current_user=Depends(require_admin)
):
    """draft → published makes the signup URL live; archived takes it down.

    Archiving does NOT touch existing tenants — they keep the features they
    paid for; it only stops new signups and hides the public product endpoint.
    """
    if body.status not in ("draft", "published", "archived"):
        raise HTTPException(status_code=400, detail="status must be draft, published or archived")
    async with get_connection() as conn:
        async with conn.transaction():
            await _snapshot(conn, product_id, current_user.email)
            row = await conn.fetchrow(
                f"""UPDATE product_definitions
                       SET status = $1, updated_at = NOW(), updated_by = $2
                     WHERE id = $3
                 RETURNING {SELECT_COLUMNS}""",
                body.status, current_user.email, product_id,
            )
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    logger.info("Admin set product %s status=%s", row["slug"], body.status)
    return row_to_product(row).to_dict()


@router.post("/products/{product_id}/sync-tenants")
async def sync_product_tenants(
    product_id: UUID,
    dry_run: bool = Query(False),
    current_user=Depends(require_admin),
):
    """Re-materialize enabled_features for ACTIVATED tenants of this product.

    Grants are materialized at signup/payment (merge_company_features is pure +
    sync and runs in pool-free workers, so there is no read-time overlay), which
    means editing a product doesn't reach the companies already on it. This is
    the deliberate catch-up.

    Only ACTIVATED tenants are touched (`is_tenant_activated` — the gate flag
    for priced products, any granted flag for contact-sales, always for free).
    A pending company must stay all-off until Stripe (or, for contact-sales,
    an admin) says otherwise, or this endpoint hands out the product for free.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT {SELECT_COLUMNS} FROM product_definitions WHERE id = $1", product_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        product = row_to_product(row)
        target = materialize_features(product)

        companies = await conn.fetch(
            "SELECT id, enabled_features FROM companies WHERE signup_source = $1",
            product.signup_source,
        )
        updated: list[str] = []
        skipped_pending = 0
        for company in companies:
            if not is_tenant_activated(product, company["enabled_features"]):
                skipped_pending += 1
                continue
            stored = company["enabled_features"]
            if isinstance(stored, str):
                try:
                    stored = json.loads(stored)
                except json.JSONDecodeError:
                    stored = {}
            stored = stored if isinstance(stored, dict) else {}
            if stored == target:
                continue
            updated.append(str(company["id"]))
            if not dry_run:
                await conn.execute(
                    "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
                    json.dumps(target), company["id"],
                )
    logger.info(
        "Admin synced product %s: %d updated, %d pending skipped (dry_run=%s)",
        product.slug, len(updated), skipped_pending, dry_run,
    )
    return {
        "dry_run": dry_run,
        "updated": len(updated),
        "skipped_pending": skipped_pending,
        "company_ids": updated,
    }


class ActivateTenant(BaseModel):
    company_id: UUID


@router.post("/products/{product_id}/activate-tenant")
async def activate_product_tenant(
    product_id: UUID, body: ActivateTenant, current_user=Depends(require_admin)
):
    """Manually activate a company on a free / contact-sales product.

    Refused for Stripe-billed products: activating those requires a completed
    checkout, exactly like admin_change_tier refuses to promote a company into
    Lite/X/Compliance without payment (admin/companies.py). Send the customer
    the signup link instead.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT {SELECT_COLUMNS} FROM product_definitions WHERE id = $1", product_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        product = row_to_product(row)
        if product.is_paid:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{product.name}' is billed through Stripe — activating it requires a completed "
                    f"checkout. Send the customer to /p/{product.slug}/signup."
                ),
            )
        company = await conn.fetchrow(
            "SELECT id, signup_source FROM companies WHERE id = $1", body.company_id
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        if company["signup_source"] != product.signup_source:
            raise HTTPException(
                status_code=400,
                detail="Company is not on this product — change its tier first",
            )
        await conn.execute(
            "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
            json.dumps(materialize_features(product)), body.company_id,
        )
    logger.info(
        "Admin activated company %s on product %s", body.company_id, product.slug
    )
    return {"ok": True}
