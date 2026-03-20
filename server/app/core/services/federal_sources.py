"""Backward-compatibility wrapper — delegates to government_apis package.

All callers (admin.py routes) import fetch_federal_sources / apply_federal_sources
from here. This wrapper keeps the existing interface intact while the implementation
lives in government_apis/.
"""

from .government_apis.orchestrator import (
    apply_government_sources as apply_federal_sources,
    fetch_government_sources as fetch_federal_sources,
)

__all__ = ["fetch_federal_sources", "apply_federal_sources"]
