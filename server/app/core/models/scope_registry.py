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
    # Sub-index reach: {"level": "county"|"city", "names": [...]}; null = whole index.
    jurisdiction_scope: Optional[Dict[str, Any]] = None


class ConfirmClassificationsRequest(BaseModel):
    item_ids: List[UUID] = Field(min_length=1)


class DispatchResponse(BaseModel):
    status: str
    dispatched_to: Literal["celery", "inline"]
    slug: Optional[str] = None
    # Is a Celery worker actually listening? A dispatch to an empty queue
    # returns 200 and then NOTHING HAPPENS — the task sits in Redis until a
    # worker starts. That is indistinguishable from success at the UI, which is
    # how "click Ingest, watch nothing change, conclude the feature is broken"
    # happens. No worker runs in local dev by default.
    worker_online: Optional[bool] = None
    message: Optional[str] = None


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


class ReviewQuarantinedRequest(BaseModel):
    """Bulk-decide grounding-quarantined rows (POST /under-review/decide).

    ``action='promote'`` sets status='active' (the admin re-read the source
    and confirmed the value); ``action='reject'`` sets status='repealed' —
    never silently deleted, it stays as an audit trail of a value that
    failed grounding and was confirmed wrong.
    """

    ids: List[UUID] = Field(min_length=1)
    action: Literal["promote", "reject"]
