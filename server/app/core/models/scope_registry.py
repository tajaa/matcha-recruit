"""Request/response shapes for the scope-registry admin API."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

Disposition = Literal["universal_in_domain", "category_specific", "conditional", "excluded"]


class ClassificationProposal(BaseModel):
    """Manual classification body (PUT /items/{id}/classification)."""

    disposition: Disposition
    applies_to_categories: List[str] = Field(default_factory=list)
    excludes_categories: List[str] = Field(default_factory=list)
    entity_condition: Optional[Dict[str, Any]] = None
    excluded_reason: Optional[str] = None
    regulation_key: Optional[str] = None
    category_slug: Optional[str] = None


class ConfirmClassificationsRequest(BaseModel):
    item_ids: List[UUID] = Field(min_length=1)


class DispatchResponse(BaseModel):
    status: str
    dispatched_to: Literal["celery", "inline"]
    slug: Optional[str] = None


class ReconcileRequest(BaseModel):
    """Codify-linkage sweep (POST /reconcile). No state = registry-wide."""

    state: Optional[str] = None
    city: Optional[str] = None


class AcknowledgeDriftRequest(BaseModel):
    """Bulk-acknowledge drift rows (POST /drift/acknowledge)."""

    ids: List[UUID] = Field(min_length=1)


class FetchQueueResearchRequest(BaseModel):
    """Drive the chain's fetch queue into research (POST /fetch-queue/research).

    ``state`` optional — no state researches the federal-only fetch queue.
    """

    state: Optional[str] = None
    city: Optional[str] = None
