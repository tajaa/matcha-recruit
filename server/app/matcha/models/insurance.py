"""Carrier quote/bind request + response models (Coterie)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Lines Coterie small-commercial can quote, expressed as limit_adequacy line keys
# so a bound policy upserts cleanly into company_coverage_lines. bop = a Business
# Owner's Policy (packaged GL + property); kept distinct so the UI can offer it.
QuotableLine = Literal["bop", "gl", "wc", "professional"]


class QuoteRequest(BaseModel):
    """Caller confirms/edits the prefilled inputs, then submits for a quote."""

    line: QuotableLine
    # Everything below defaults from the company's own data via
    # coterie_service.build_quote_request; the caller may override before submit.
    legal_name: Optional[str] = Field(None, max_length=255)
    naics: Optional[str] = Field(None, max_length=10)
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    headcount: Optional[int] = Field(None, ge=0)
    annual_payroll: Optional[float] = Field(None, ge=0)
    annual_revenue: Optional[float] = Field(None, ge=0)


class QuoteResponse(BaseModel):
    id: str
    line: str
    carrier: str
    status: str
    quote_ref: Optional[str] = None
    premium_cents: Optional[int] = None
    expires_at: Optional[str] = None
    error_message: Optional[str] = None
    certificate_id: Optional[str] = None
    created_at: Optional[str] = None
