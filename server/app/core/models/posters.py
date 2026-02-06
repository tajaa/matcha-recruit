"""Pydantic models for compliance poster templates and orders."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- Template models ---

class PosterTemplateResponse(BaseModel):
    id: UUID
    jurisdiction_id: UUID
    title: str
    description: Optional[str] = None
    version: int
    pdf_url: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    categories_included: Optional[list[str]] = None
    requirement_count: int = 0
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Joined fields
    jurisdiction_name: Optional[str] = None
    state: Optional[str] = None


class PosterTemplateListResponse(BaseModel):
    templates: list[PosterTemplateResponse]
    total: int


# --- Order models ---

class PosterOrderCreate(BaseModel):
    location_id: UUID
    template_ids: list[UUID] = Field(..., min_length=1)
    quantity: int = Field(default=1, ge=1, le=100)
    shipping_address: Optional[str] = None


class PosterOrderItemResponse(BaseModel):
    id: UUID
    template_id: UUID
    quantity: int
    template_title: Optional[str] = None
    jurisdiction_name: Optional[str] = None


class PosterOrderResponse(BaseModel):
    id: UUID
    company_id: UUID
    location_id: UUID
    status: str
    requested_by: Optional[UUID] = None
    admin_notes: Optional[str] = None
    quote_amount: Optional[float] = None
    shipping_address: Optional[str] = None
    tracking_number: Optional[str] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Joined fields
    company_name: Optional[str] = None
    location_name: Optional[str] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    requested_by_email: Optional[str] = None
    items: list[PosterOrderItemResponse] = []


class PosterOrderListResponse(BaseModel):
    orders: list[PosterOrderResponse]
    total: int


class PosterOrderUpdate(BaseModel):
    status: Optional[str] = None
    admin_notes: Optional[str] = None
    quote_amount: Optional[float] = None
    tracking_number: Optional[str] = None


# --- Available posters for client view ---

class AvailablePoster(BaseModel):
    location_id: UUID
    location_name: Optional[str] = None
    location_city: str
    location_state: str
    jurisdiction_id: Optional[UUID] = None
    template_id: Optional[UUID] = None
    template_title: Optional[str] = None
    template_status: Optional[str] = None
    template_version: Optional[int] = None
    pdf_url: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    categories_included: Optional[list[str]] = None
    has_active_order: bool = False
