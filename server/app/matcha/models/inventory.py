from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

MovementKind = Literal["out", "in", "stockout", "adjust"]
OrderStatus = Literal["queued", "ordered", "received", "cancelled"]


class OrderOut(BaseModel):
    id: UUID
    item_id: UUID
    status: OrderStatus
    suggested_quantity: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    suggestion: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class InventoryItemOut(BaseModel):
    id: UUID
    name: str
    unit: Optional[str] = None
    current_quantity: Optional[Decimal] = None
    low_stock_threshold: Optional[Decimal] = None
    auto_created: bool
    archived_at: Optional[datetime] = None
    location_id: Optional[UUID] = None
    location_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    open_order: Optional[OrderOut] = None


class InventoryItemCreate(BaseModel):
    name: str
    unit: Optional[str] = None
    current_quantity: Optional[Decimal] = None
    low_stock_threshold: Optional[Decimal] = None
    location_id: Optional[UUID] = None


class InventoryItemPatch(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    low_stock_threshold: Optional[Decimal] = None
    set_quantity: Optional[Decimal] = None
    archived: Optional[bool] = None


class MovementOut(BaseModel):
    id: UUID
    item_id: UUID
    kind: MovementKind
    quantity: Optional[Decimal] = None
    quantity_delta: Optional[Decimal] = None
    quantity_estimated: bool
    note: Optional[str] = None
    narrative: str
    created_at: datetime


class OrderCreate(BaseModel):
    item_id: UUID
    quantity: Optional[Decimal] = None


class OrderAction(BaseModel):
    quantity: Optional[Decimal] = None


class ItemListResponse(BaseModel):
    items: list[InventoryItemOut]


class MovementListResponse(BaseModel):
    movements: list[MovementOut]


class OrderListResponse(BaseModel):
    orders: list[OrderOut]
