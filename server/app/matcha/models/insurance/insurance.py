"""Carrier quote/bind request + response models (Coterie)."""

from typing import Literal, Optional
from uuid import UUID

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


# --- broker-placed quoting (Broker Quoting Desk) -------------------------------

class BrokerQuoteRequest(QuoteRequest):
    """A broker requesting a quote on behalf of a client in their book. Same
    prefill/override fields as a client self-serve quote, plus placement metadata
    the broker sets (commission + a private note)."""

    commission_bps: Optional[int] = Field(None, ge=0, le=10_000)
    broker_note: Optional[str] = Field(None, max_length=2_000)


class PresentRequest(BaseModel):
    """Broker presents a quoted policy to the on-platform client for acceptance."""

    commission_bps: Optional[int] = Field(None, ge=0, le=10_000)
    broker_note: Optional[str] = Field(None, max_length=2_000)


class FnolRequest(BaseModel):
    """File a First Notice of Loss to the carrier from a logged IR incident."""

    incident_id: UUID
    description: Optional[str] = Field(None, max_length=4_000)
