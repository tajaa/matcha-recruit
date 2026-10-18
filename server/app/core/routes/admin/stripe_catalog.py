"""Admin controls for the two supported commercial Stripe catalog products."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import require_admin
from app.core.models.stripe_catalog import StripeCatalogDetails
from app.core.services import stripe_catalog as catalog

router = APIRouter()


@router.get("/stripe-catalog")
async def get_stripe_catalog(current_user=Depends(require_admin)):
    try:
        return await catalog.catalog_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not read the Stripe catalog. Check the server's Stripe configuration.") from exc


@router.post("/stripe-catalog/webhook")
async def connect_stripe_catalog_webhook(current_user=Depends(require_admin)):
    try:
        return await catalog.configure_catalog_webhook()
    except catalog.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Stripe webhook setup failed. Retry after checking the Stripe configuration.") from exc


@router.post("/stripe-catalog/{product_key}/sync")
async def sync_stripe_catalog_product(product_key: str, current_user=Depends(require_admin)):
    if product_key not in catalog.PRODUCTS:
        raise HTTPException(status_code=404, detail="Only Matcha Incidents and Matcha Scheduler have a commercial catalog")
    try:
        await catalog.sync_product(product_key, changed_by=current_user.email)
        return await catalog.catalog_status()
    except catalog.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Stripe sync failed. The admin price is saved; retry syncing this product.") from exc


@router.put("/stripe-catalog/{product_key}")
async def update_stripe_catalog_details(product_key: str, body: StripeCatalogDetails, current_user=Depends(require_admin)):
    if product_key not in catalog.PRODUCTS:
        raise HTTPException(status_code=404, detail="This product is in beta and has no commercial Stripe catalog")
    try:
        await catalog.save_catalog_details(product_key, **body.model_dump(), changed_by=current_user.email)
        return await catalog.catalog_status()
    except catalog.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not save or sync product details. Reload and retry.") from exc
