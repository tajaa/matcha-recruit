"""Who gets the Espresso assistant.

The assistant belongs to Espresso, the personal product, not to business
Matcha: it is on for every personal account (`companies.is_personal`) and
never for a business workspace, so there is no company flag to switch. Plan
limits still apply on top (`entitlements_service`: Pro and up).

No I/O and nothing heavy imported, so the channel access check can use it.
"""
from __future__ import annotations

from typing import Mapping


def assistant_available(*, is_personal: bool | None, features: Mapping[str, bool]) -> bool:
    return bool(is_personal) and bool(features.get("matcha_work"))
