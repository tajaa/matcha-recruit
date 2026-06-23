"""Commercial-property request models (Statement of Values)."""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ISO construction classes (best → worst handled in property_sov.CONSTRUCTION_GRADE).
ConstructionType = Literal[
    "frame", "joisted_masonry", "non_combustible",
    "masonry_non_combustible", "modified_fire_resistive", "fire_resistive",
]


class BuildingUpsert(BaseModel):
    """One building on the company's Statement of Values (COPE + values)."""

    location_id: Optional[UUID] = None
    name: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=2)
    zipcode: Optional[str] = Field(default=None, max_length=10)
    county: Optional[str] = Field(default=None, max_length=120)
    occupancy: Optional[str] = Field(default=None, max_length=120)
    # COPE
    construction_type: Optional[ConstructionType] = None
    year_built: Optional[int] = Field(default=None, ge=1700, le=2100)
    sq_ft: Optional[int] = Field(default=None, ge=0)
    stories: Optional[int] = Field(default=None, ge=0)
    roof_year: Optional[int] = Field(default=None, ge=1700, le=2100)
    sprinklered: bool = False
    protection_class: Optional[str] = Field(default=None, max_length=4)
    # values
    building_value: Optional[float] = Field(default=None, ge=0)
    contents_value: Optional[float] = Field(default=None, ge=0)
    bi_value: Optional[float] = Field(default=None, ge=0)
    replacement_cost: Optional[float] = Field(default=None, ge=0)
    insured_value: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None


class BuildingBulkInsert(BaseModel):
    """A reviewed list of buildings to insert in one shot (parse → review → import)."""

    buildings: list[BuildingUpsert] = Field(default_factory=list, max_length=1000)


class BulkUploadResult(BaseModel):
    """Per-row result of a CSV upload / bulk insert (mirrors BulkEmployeeCSVUpload)."""

    total_rows: int
    created: int
    failed: int
    errors: list[dict]   # [{row: int, name: str, error: str}]
    ids: list[str]
