"""Scope Registry — authority-anchored (jurisdiction × business-category) scoping.

Decides which regulations a business is liable for, before any values are
fetched. Companion docs at repo root: SCOPE_REGISTRY_PLAN.md (this package's
design) and EVAL_SYSTEM.md (the eval suites that verify the catalog it feeds).

Phase-1 commit 2 ships only the canonical business-category taxonomy
(`categories.py`) plus the `scoperg01` schema. Ingest, classification, strata,
and resolution land in later commits.
"""
