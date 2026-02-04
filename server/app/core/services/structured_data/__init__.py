"""Tier 1 Structured Data Sources service for compliance data."""

from .service import StructuredDataService
from .sources import SOURCE_REGISTRY

__all__ = ["StructuredDataService", "SOURCE_REGISTRY"]
