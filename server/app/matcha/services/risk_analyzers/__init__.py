"""Risk Pilot deterministic analysis engine.

A pluggable registry of analyzer packs (volatility, financial ratios, insurance
loss, inventory) over a single normalized data model, plus CSV/XLSX/document
parsing, corpus assembly, and cross-dataset comparison. All math is Python
stdlib only — no numpy/pandas/scipy. Pure and unit-tested; the router/service
layer adds DB, Gemini narration, and PDF rendering on top.
"""

from .base import Analyzer, run_analyzers, slug
from .parse import parse_tabular, parsed_from_extraction, normalize, downsample_for_storage
from .mapping import map_roles, guess_role, infer_kind, CANONICAL_ROLES
from .corpus import build_corpus
from .compare import build_comparison

__all__ = [
    "Analyzer", "run_analyzers", "slug",
    "parse_tabular", "parsed_from_extraction", "normalize", "downsample_for_storage",
    "map_roles", "guess_role", "infer_kind", "CANONICAL_ROLES",
    "build_corpus", "build_comparison",
]
