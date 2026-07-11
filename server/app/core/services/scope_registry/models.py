"""Pydantic shapes for the scope-registry authority layer.

Response/DTO models for authority indexes and their enumerated items. The
classification primitive (`authority_item_classifications`) is commit 4 — this
commit only enumerates the corpus.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

SourceType = Literal["ecfr", "federal_register", "curated"]


class AuthorityItem(BaseModel):
    """One enumerated citation within an authority index.

    Not consumed by the ingest layer (which passes plain dicts to asyncpg) —
    this and `AuthorityIndex` are the response shapes for the commit-4 admin
    endpoints (`GET /admin/scope-registry/authority*`).

    ``parent_citation`` links a section to its subpart (or a subpart to its
    part); the ingest layer resolves it to ``parent_item_id`` at write time.
    ``hierarchy`` mirrors the JSONB column: ``{title, part, subpart, section}``
    with absent levels omitted.
    """

    citation: str
    heading: Optional[str] = None
    hierarchy: Dict[str, str] = Field(default_factory=dict)
    parent_citation: Optional[str] = None
    source_url: Optional[str] = None
    amendment_date: Optional[date] = None


class AuthorityIndex(BaseModel):
    id: Optional[UUID] = None
    slug: str
    name: str
    level: str
    jurisdiction_id: Optional[UUID] = None
    source_type: SourceType
    domain_categories: List[str] = Field(default_factory=list)
    domain_excludes: List[str] = Field(default_factory=list)
    enumerable: bool = False
    item_count: int = 0
    unclassified_count: int = 0
    last_ingested_at: Optional[datetime] = None


class IngestResult(BaseModel):
    """Outcome of one ingest run, returned by the task + service."""

    slug: str
    source_type: SourceType
    items_upserted: int
    item_count: int
    unclassified_count: int
    enumerable: bool
    # Drift vs the previous ingest of this index — the "a new/changed/repealed
    # federal section appeared" signal. All zero on an index's first ingest
    # (no baseline to diff against).
    new_count: int = 0
    amended_count: int = 0
    removed_count: int = 0
