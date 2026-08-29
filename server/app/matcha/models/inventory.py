from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer


JsonDecimal = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]

MovementKind = Literal["out", "in", "stockout", "adjust", "sale", "waste"]
WasteReason = Literal[
    "spoilage", "expired", "prep_error", "overproduction",
    "breakage", "contamination", "theft", "comp", "recall", "unknown",
]
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
    category: Optional[str] = None
    shelf_life_days: Optional[int] = None
    yield_pct: Optional[Decimal] = None
    par_source: Literal["manual", "auto"] = "manual"
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
    category: Optional[str] = Field(default=None, max_length=60)
    shelf_life_days: Optional[int] = Field(default=None, ge=1, le=3650)
    yield_pct: Optional[Decimal] = Field(default=None, gt=0, le=1)
    par_source: Literal["manual", "auto"] = "manual"
    location_id: Optional[UUID] = None


class InventoryItemPatch(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    low_stock_threshold: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = Field(default=None, ge=0)
    category: Optional[str] = Field(default=None, max_length=60)
    shelf_life_days: Optional[int] = Field(default=None, ge=1, le=3650)
    yield_pct: Optional[Decimal] = Field(default=None, gt=0, le=1)
    par_source: Optional[Literal["manual", "auto"]] = None
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
    waste_reason: Optional[WasteReason] = None
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
    expires_on: Optional[date] = None    # per-line override; falls back to shelf_life_days if unset


class ReceiptCommit(BaseModel):
    location_id: Optional[UUID] = None
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    received_on: Optional[date] = None   # reviewed receipt date; defaults to today if unset
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
    import_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    business_date: Optional[str] = None
    source: Literal["upload", "email", "square", "toast"] = "upload"
    filename: Optional[str] = None
    gmail_message_id: Optional[str] = None
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
    wasted: Decimal = Decimal("0")


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


class ForecastOverrideInput(BaseModel):
    week_start: date
    demand_multiplier: Decimal = Field(ge=Decimal("0.5"), le=Decimal("2.0"))
    reason: str = Field(min_length=1, max_length=500)
    source: Literal["manual", "ai_accepted"] = "manual"
    confidence: Optional[Literal["low", "medium", "high"]] = None


class ForecastSettingsUpsert(BaseModel):
    location_id: Optional[UUID] = None
    horizon_days: int = Field(default=56, ge=14, le=90)
    history_days: int = Field(default=90, ge=28, le=365)
    default_lead_time_days: int = Field(default=7, ge=0, le=180)
    default_safety_stock_days: int = Field(default=7, ge=0, le=180)
    timezone: str = Field(default="America/Los_Angeles", min_length=1, max_length=80)
    par_auto_apply: bool = False
    par_max_drift_pct: Decimal = Field(default=Decimal("0.5"), gt=0, le=5)


class ForecastRuleUpsert(BaseModel):
    lead_time_days: int = Field(ge=0, le=180)
    safety_stock_days: int = Field(ge=0, le=180)
    case_pack_quantity: Decimal = Field(gt=0)
    minimum_order_quantity: Decimal = Field(default=Decimal("0"), ge=0)


class ForecastPreviewRequest(BaseModel):
    location_id: Optional[UUID] = None
    forecast_start: Optional[date] = None
    overrides: list[ForecastOverrideInput] = Field(default_factory=list, max_length=12)


class ForecastRunCreate(ForecastPreviewRequest):
    pass


class ForecastParApply(BaseModel):
    item_ids: Optional[list[UUID]] = None
    mode: Literal["manual", "huume"] = "manual"


class ForecastParAIDraft(BaseModel):
    run_id: UUID


class ForecastAIDraftRequest(BaseModel):
    location_id: Optional[UUID] = None
    horizon_start: Optional[date] = None
    manager_context: str = Field(min_length=1, max_length=4000)


class ForecastNetworkSummaryOut(BaseModel):
    location_count: int
    matched_item_groups: int
    transfer_count: int
    shortages_fully_covered: int
    remaining_reorder_count: int
    attention_count: int
    inventory_value_moved: Optional[JsonDecimal] = None


class ForecastNetworkTransferOut(BaseModel):
    item_name: str
    unit: Optional[str] = None
    quantity: JsonDecimal
    from_item_id: UUID
    from_location_id: UUID
    from_location_name: str
    from_current_quantity: JsonDecimal
    from_target_quantity: JsonDecimal
    from_post_transfer_quantity: JsonDecimal
    to_item_id: UUID
    to_location_id: UUID
    to_location_name: str
    to_current_quantity: JsonDecimal
    to_target_quantity: JsonDecimal
    to_post_transfer_quantity: JsonDecimal
    receiver_remaining_shortage: JsonDecimal
    runout_date: Optional[date] = None
    order_by_date: Optional[date] = None
    days_of_cover_added: Optional[JsonDecimal] = None
    inventory_value: Optional[JsonDecimal] = None
    coverage: Literal["full", "partial"]
    confidence: Literal["low", "medium", "high"]
    rationale: str


class ForecastNetworkShortageOut(BaseModel):
    item_id: UUID
    item_name: str
    unit: Optional[str] = None
    location_id: UUID
    location_name: str
    shortage_quantity: JsonDecimal
    suggested_order_quantity: JsonDecimal
    runout_date: Optional[date] = None
    order_by_date: Optional[date] = None
    confidence: Literal["low", "medium", "high"]


class ForecastNetworkAttentionOut(BaseModel):
    item_id: UUID
    item_name: str
    location_id: UUID
    location_name: str
    status: Literal["count_required", "insufficient_history"]


class ForecastNetworkPlanOut(BaseModel):
    forecast_start: date
    summary: ForecastNetworkSummaryOut
    transfers: list[ForecastNetworkTransferOut]
    remaining_shortages: list[ForecastNetworkShortageOut]
    attention: list[ForecastNetworkAttentionOut]


class POSLocationBindingUpsert(BaseModel):
    external_location_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    location_id: UUID


class POSSalesSyncRequest(BaseModel):
    start_date: date
    end_date: date


class POSMappingUpsert(BaseModel):
    external_item_id: str = Field(min_length=1, max_length=200)
    mapping_id: UUID
