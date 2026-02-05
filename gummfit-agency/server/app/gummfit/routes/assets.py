"""GumFit asset routes for marketing/landing page image management."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from ...database import get_connection
from ...services.storage import get_storage
from ..dependencies import require_gumfit_admin
from ..models.asset import (
    GumfitAssetResponse,
    GumfitAssetListResponse,
    GumfitAssetUpdate,
    AssetCategory,
)

router = APIRouter()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload", response_model=GumfitAssetResponse)
async def upload_asset(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form(default=AssetCategory.GENERAL),
    alt_text: Optional[str] = Form(default=None),
    current_user: dict = Depends(require_gumfit_admin),
):
    """Upload a new marketing asset."""
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
        )

    # Read file content
    file_bytes = await file.read()
    file_size = len(file_bytes)

    # Validate file size
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # Upload to storage
    storage = get_storage()
    url = await storage.upload_file(file_bytes, file.filename, "gumfit-assets")

    # Get image dimensions if possible
    width, height = None, None
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(file_bytes))
        width, height = img.size
    except Exception:
        pass  # Not critical if we can't get dimensions

    # Save to database
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO gumfit_assets (name, url, category, file_type, file_size, width, height, alt_text, uploaded_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id, name, url, category, file_type, file_size, width, height, alt_text, uploaded_by, created_at, updated_at
            """,
            name,
            url,
            category,
            file.content_type,
            file_size,
            width,
            height,
            alt_text,
            current_user.id,
        )

    return GumfitAssetResponse(**dict(row))


@router.get("", response_model=GumfitAssetListResponse)
async def list_assets(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _: dict = Depends(require_gumfit_admin),
):
    """List all marketing assets with optional filtering."""
    async with get_connection() as conn:
        # Build query
        where_clauses = []
        params = []
        param_idx = 1

        if category:
            where_clauses.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if search:
            where_clauses.append(f"(name ILIKE ${param_idx} OR alt_text ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM gumfit_assets {where_sql}"
        total = await conn.fetchval(count_query, *params)

        # Get assets
        params.extend([limit, offset])
        query = f"""
            SELECT id, name, url, category, file_type, file_size, width, height, alt_text, uploaded_by, created_at, updated_at
            FROM gumfit_assets
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        rows = await conn.fetch(query, *params)

    assets = [GumfitAssetResponse(**dict(row)) for row in rows]
    return GumfitAssetListResponse(assets=assets, total=total)


@router.get("/{asset_id}", response_model=GumfitAssetResponse)
async def get_asset(
    asset_id: UUID,
    _: dict = Depends(require_gumfit_admin),
):
    """Get a single asset by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, url, category, file_type, file_size, width, height, alt_text, uploaded_by, created_at, updated_at
            FROM gumfit_assets WHERE id = $1
            """,
            asset_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")

    return GumfitAssetResponse(**dict(row))


@router.patch("/{asset_id}", response_model=GumfitAssetResponse)
async def update_asset(
    asset_id: UUID,
    update: GumfitAssetUpdate,
    _: dict = Depends(require_gumfit_admin),
):
    """Update asset metadata."""
    async with get_connection() as conn:
        # Check if asset exists
        existing = await conn.fetchval("SELECT id FROM gumfit_assets WHERE id = $1", asset_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Asset not found")

        # Build update query
        updates = []
        params = []
        param_idx = 1

        if update.name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(update.name)
            param_idx += 1

        if update.category is not None:
            updates.append(f"category = ${param_idx}")
            params.append(update.category)
            param_idx += 1

        if update.alt_text is not None:
            updates.append(f"alt_text = ${param_idx}")
            params.append(update.alt_text)
            param_idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        params.append(asset_id)

        query = f"""
            UPDATE gumfit_assets SET {', '.join(updates)}
            WHERE id = ${param_idx}
            RETURNING id, name, url, category, file_type, file_size, width, height, alt_text, uploaded_by, created_at, updated_at
        """
        row = await conn.fetchrow(query, *params)

    return GumfitAssetResponse(**dict(row))


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: UUID,
    _: dict = Depends(require_gumfit_admin),
):
    """Delete an asset."""
    async with get_connection() as conn:
        # Get asset URL before deleting
        row = await conn.fetchrow("SELECT url FROM gumfit_assets WHERE id = $1", asset_id)
        if not row:
            raise HTTPException(status_code=404, detail="Asset not found")

        # Delete from storage
        storage = get_storage()
        try:
            url = row["url"]
            await storage.delete_file(url)
        except Exception:
            pass  # Don't fail if storage delete fails

        # Delete from database
        await conn.execute("DELETE FROM gumfit_assets WHERE id = $1", asset_id)

    return {"status": "deleted", "id": str(asset_id)}


@router.get("/categories/list")
async def list_categories(
    _: dict = Depends(require_gumfit_admin),
):
    """List available asset categories."""
    return {
        "categories": [
            {"value": AssetCategory.GENERAL, "label": "General"},
            {"value": AssetCategory.HERO, "label": "Hero Images"},
            {"value": AssetCategory.FEATURE, "label": "Feature Images"},
            {"value": AssetCategory.LOGO, "label": "Logos"},
            {"value": AssetCategory.BACKGROUND, "label": "Backgrounds"},
            {"value": AssetCategory.ICON, "label": "Icons"},
        ]
    }
