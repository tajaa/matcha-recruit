from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

MovementKind = Literal["out", "in", "stockout", "adjust", "sale"]
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
    unit_cost: Optional[Decimal] = None
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
    unit_cost: Optional[Decimal] = Field(default=None, ge=0)
    location_id: Optional[UUID] = None


class InventoryItemPatch(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    low_stock_threshold: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = Field(default=None, ge=0)
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


class ReceiptCommitLine(BaseModel):
    item_id: Optional[UUID] = None       # existing item ...
    new_item_name: Optional[str] = None  # ... or create-new (exactly one required)
    quantity: float = Field(gt=0)        # the user-CONFIRMED count (invoice figure is only the prefill)
    order_id: Optional[UUID] = None      # open order to mark_received against


class ReceiptCommit(BaseModel):
    location_id: Optional[UUID] = None
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    force: bool = False                  # override the duplicate_invoice 409
    lines: list[ReceiptCommitLine]


class ReceiptCommitResult(BaseModel):
    total_rows: int
    created: int
    failed: int
    errors: list[dict]
    ids: list[str]                       # movement ids written


class AuditLine(BaseModel):
    item_id: Optional[UUID] = None       # existing item ...
    new_item_name: Optional[str] = None  # ... or accept-as-new (exactly one required)
    counted_quantity: float = Field(ge=0)  # the manager's physical count; 0 is legal (none on hand)


class AuditCommit(BaseModel):
    location_id: Optional[UUID] = None
    note: Optional[str] = None           # defaults server-side to "Stock audit"
    lines: list[AuditLine]


class AuditCommitResult(BaseModel):
    total: int
    applied: int
    failed: int
    errors: list[dict]                   # [{row, item, error}]
    variance: Optional[dict] = None


class SalesMappingComponent(BaseModel):
    item_id: UUID
    quantity_per_sale: float = Field(gt=0)
    unit: Optional[str] = None


class SalesMappingUpsert(BaseModel):
    sold_name: str = Field(min_length=1, max_length=200)
    kind: Literal["direct", "recipe", "ignore"]
    components: list[SalesMappingComponent] = Field(default_factory=list)
    location_id: Optional[UUID] = None


class SalesSourceUpsert(BaseModel):
    from_address: str = Field(min_length=3, max_length=320)
    subject_match: Optional[str] = Field(default=None, max_length=200)
    location_id: Optional[UUID] = None


class SalesLine(BaseModel):
    sold_name: str = Field(min_length=1, max_length=200)
    quantity: float
    gross_sales: Optional[float] = None
    mapping_id: Optional[UUID] = None
    item_id: Optional[UUID] = None
    quantity_per_sale: Optional[float] = Field(default=None, gt=0)
    components: list[SalesMappingComponent] = Field(default_factory=list)
    new_mapping: Optional[SalesMappingUpsert] = None
    status: Literal["mapped", "unmapped", "ignored"] = "unmapped"


class SalesCommit(BaseModel):
    location_id: Optional[UUID] = None
    business_date: Optional[str] = None
    source: Literal["upload", "email"] = "upload"
    filename: Optional[str] = None
    gmail_message_id: Optional[str] = None
    force: bool = False
    lines: list[SalesLine]


class SalesCommitResult(BaseModel):
    import_id: UUID
    total: int
    mapped: int
    unmapped: int
    items_affected: int
    errors: list[dict]


class AuditSheetRow(BaseModel):
    item: InventoryItemOut
    expected: Optional[Decimal] = None
    baseline: Optional[Decimal] = None
    baseline_at: Optional[datetime] = None
    received: Decimal = Decimal("0")
    sold: Decimal = Decimal("0")
    manual_out: Decimal = Decimal("0")
    stockouts: Decimal = Decimal("0")


class AuditRunOut(BaseModel):
    id: UUID
    company_id: UUID
    location_id: Optional[UUID] = None
    committed_by: Optional[UUID] = None
    committed_at: datetime
    note: Optional[str] = None
    line_count: int
    variance_units: Optional[Decimal] = None
    variance_value: Optional[Decimal] = None


class VoiceCountLine(BaseModel):
    item_name: str
    quantity: float
    unit: Optional[str] = None
    item_id: Optional[str] = None
    matched_name: Optional[str] = None
    exact: bool = False


class VoiceCountDraft(BaseModel):
    available: bool
    transcript: Optional[str] = None
    model: Optional[str] = None
    lines: list[VoiceCountLine]
