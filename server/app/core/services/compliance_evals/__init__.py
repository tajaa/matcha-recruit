"""Compliance-data evaluation suites.

Measures the jurisdiction catalog rather than participating in it: completeness
per (jurisdiction × industry), citation authority, tag/key organization, and
agreement with hand-verified golden facts. Read-only over
``jurisdiction_requirements``.
"""
from .runner import (
    ALL_SUITES,
    NETWORK_SUITES,
    network_suites,
    onboarding_readiness,
    run_evals,
)

__all__ = ["ALL_SUITES", "NETWORK_SUITES", "network_suites", "run_evals",
           "onboarding_readiness"]
