"""Limit-adequacy + contract-review request models."""

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

IndemnityForm = Literal["broad", "intermediate", "limited", "unclear"]
IndemnityDirection = Literal["we_indemnify_them", "they_indemnify_us", "mutual", "unclear"]
ContractType = Literal["lease", "construction", "vendor_service", "msa", "other"]


class CoverageLineUpdate(BaseModel):
    """Limits the company carries for one line (upserted by line key)."""

    carrier: Optional[str] = Field(None, max_length=255)
    per_occurrence: Optional[float] = Field(None, ge=0)
    aggregate: Optional[float] = Field(None, ge=0)
    retention: Optional[float] = Field(None, ge=0)
    additional_insured: bool = False
    waiver_of_subrogation: bool = False
    primary_noncontributory: bool = False
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    note: Optional[str] = Field(None, max_length=2000)


class ContractRequirement(BaseModel):
    """One insurance requirement a contract imposes (a row in requirements[])."""

    line: str = Field(..., max_length=40)
    per_occurrence: Optional[float] = Field(None, ge=0)
    aggregate: Optional[float] = Field(None, ge=0)
    additional_insured: bool = False
    waiver_of_subrogation: bool = False
    primary_noncontributory: bool = False
    note: Optional[str] = Field(None, max_length=1000)
    quote: Optional[str] = Field(None, max_length=2000)
    page: Optional[int] = Field(None, ge=1)


class Indemnity(BaseModel):
    """The indemnification clause as extracted (and human-corrected)."""

    present: bool = False
    form: IndemnityForm = "unclear"
    direction: IndemnityDirection = "unclear"
    covers_sole_negligence: bool = False
    defense_obligation: bool = False
    quote: Optional[str] = Field(None, max_length=2000)
    page: Optional[int] = Field(None, ge=1)


class RiskTransfer(BaseModel):
    """Risk-transfer provisions stored on ``company_contracts.risk_transfer``."""

    indemnity: Indemnity = Field(default_factory=Indemnity)


class ContractCreate(BaseModel):
    """Create/replace a contract record (manual entry path)."""

    name: str = Field(..., min_length=1, max_length=255)
    counterparty: Optional[str] = Field(None, max_length=255)
    requirements: List[ContractRequirement] = Field(default_factory=list)
    contract_type: Optional[ContractType] = None
    governing_state: Optional[str] = Field(None, min_length=2, max_length=2)
    project_state: Optional[str] = Field(None, min_length=2, max_length=2)
    risk_transfer: Optional[RiskTransfer] = None


class ContractUpdate(BaseModel):
    """Edit a contract — confirm/adjust the parsed requirements + risk transfer.

    Any edit that carries ``risk_transfer`` resets the confirmation stamp (the
    human vouched for the *old* clause, not this one)."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    counterparty: Optional[str] = Field(None, max_length=255)
    requirements: Optional[List[ContractRequirement]] = None
    contract_type: Optional[ContractType] = None
    governing_state: Optional[str] = Field(None, min_length=2, max_length=2)
    project_state: Optional[str] = Field(None, min_length=2, max_length=2)
    risk_transfer: Optional[RiskTransfer] = None
