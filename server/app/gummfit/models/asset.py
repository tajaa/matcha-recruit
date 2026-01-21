"""GumFit asset models for marketing/landing page images."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AssetCategory:
    """Asset category constants."""
    GENERAL = "general"
    HERO = "hero"
    FEATURE = "feature"
    LOGO = "logo"
    BACKGROUND = "background"
    ICON = "icon"


class GumfitAssetCreate(BaseModel):
    """Request model for creating an asset."""
    name: str
    category: str = AssetCategory.GENERAL
    alt_text: Optional[str] = None


class GumfitAssetUpdate(BaseModel):
    """Request model for updating an asset."""
    name: Optional[str] = None
    category: Optional[str] = None
    alt_text: Optional[str] = None


class GumfitAssetResponse(BaseModel):
    """Response model for an asset."""
    id: UUID
    name: str
    url: str
    category: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    alt_text: Optional[str] = None
    uploaded_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GumfitAssetListResponse(BaseModel):
    """Response model for listing assets."""
    assets: list[GumfitAssetResponse]
    total: int
