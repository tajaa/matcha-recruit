from typing import Optional, Any

from pydantic import BaseModel


class BulkImportError(BaseModel):
    """Error details for a single row in bulk import."""
    row: int
    error: str
    data: Optional[dict[str, Any]] = None


class BulkImportResult(BaseModel):
    """Result of a bulk import operation."""
    success_count: int
    error_count: int
    errors: list[BulkImportError]
    imported_ids: list[str]


class CompanyBulkRow(BaseModel):
    """Schema for a single company row in bulk import."""
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None


class PositionBulkRow(BaseModel):
    """Schema for a single position row in bulk import."""
    company_name: str  # Used to look up or create company
    title: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = "USD"
    location: Optional[str] = None
    employment_type: Optional[str] = None
    required_skills: Optional[str] = None  # Comma-separated for CSV
    preferred_skills: Optional[str] = None  # Comma-separated for CSV
    experience_level: Optional[str] = None
    requirements: Optional[str] = None  # Comma-separated for CSV
    responsibilities: Optional[str] = None  # Comma-separated for CSV
    benefits: Optional[str] = None  # Comma-separated for CSV
    department: Optional[str] = None
    reporting_to: Optional[str] = None
    remote_policy: Optional[str] = None
    visa_sponsorship: Optional[bool] = False
