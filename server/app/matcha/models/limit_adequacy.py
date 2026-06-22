"""Limit-adequacy + contract-review request models."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


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


class ContractCreate(BaseModel):
    """Create/replace a contract record (manual entry path)."""

    name: str = Field(..., min_length=1, max_length=255)
    counterparty: Optional[str] = Field(None, max_length=255)
    requirements: List[ContractRequirement] = Field(default_factory=list)


class ContractUpdate(BaseModel):
    """Edit a contract — confirm/adjust the parsed requirements."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    counterparty: Optional[str] = Field(None, max_length=255)
    requirements: Optional[List[ContractRequirement]] = None
