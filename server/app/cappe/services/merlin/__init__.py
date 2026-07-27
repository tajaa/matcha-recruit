"""Merlin — AI chat/agent editing for Cappe sites.

No eager re-exports here (would re-tighten the turn.py <-> routing.py cycle
that `routing.resolve_model_tier` lazily breaks) — import submodules directly,
e.g. `from ..services.merlin import store as merlin_store`.
"""
