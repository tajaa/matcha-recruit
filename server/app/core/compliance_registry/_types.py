from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComplianceCategoryDef:
    key: str
    label: str
    short_label: str
    group: str          # "labor" | "healthcare" | "oncology" | "medical_compliance" | "supplementary"
    industry_tag: str   # e.g. "healthcare:pharmacy" or "" for labor
    research_mode: str  # "default_sweep" | "specialty" | "health_specs"
    docx_section: Optional[int]


@dataclass(frozen=True)
class RegulationDef:
    key: str
    category: str
    name: str
    description: str
    enforcing_agency: str
    state_variance: str      # "High" | "Moderate" | "Low/None"
    update_frequency: str
    authority_sources: tuple  # tuple of dicts


