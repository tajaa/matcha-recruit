"""Pure, DB-free authz + reply-parsing rules for the @huume inventory flow.
InventoryVerdict mirrors schedule_chat_rules.ScheduleVerdict exactly —
same two-stage pattern (role -> flag -> stage-specific check)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

APPROVE_ROLES = frozenset({"client", "admin"})

_INVENTORY_OFF_MESSAGE = "Inventory tracking isn't turned on for this workspace."
_APPROVE_ONLY_MESSAGE = (
    "Only a manager can approve or cancel an order — an admin can do that "
    "from the Inventory page or by replying here."
)


@dataclass(frozen=True)
class InventoryVerdict:
    kind: Literal["proceed", "refuse"]
    reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.kind == "proceed"


def evaluate_inventory_action(
    *, role: Optional[str], features: dict, stage: Literal["movement", "approve_order"],
) -> InventoryVerdict:
    """movement: any channel member (any role) may record a deduction/
    receipt/stockout, as long as `inventory` is enabled. approve_order:
    role must be client/admin, same pair as scheduling's ALLOWED_ROLES."""
    if not features.get("inventory"):
        return InventoryVerdict("refuse", _INVENTORY_OFF_MESSAGE)
    if stage == "approve_order" and role not in APPROVE_ROLES:
        return InventoryVerdict("refuse", _APPROVE_ONLY_MESSAGE)
    return InventoryVerdict("proceed")


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "a dozen": 12, "dozen": 12, "a couple": 2,
    "couple": 2, "a few": 3, "few": 3,
}
_NUMERIC_RE = re.compile(r"(\d+(?:\.\d+)?)")


def parse_quantity_reply(text: str) -> Optional[Decimal]:
    """First bare number in the reply ("12", "about 12", "12 boxes"), or a
    recognized small number word ("a dozen" -> 12). None when nothing
    parses (e.g. "yes", ""). Numeric check runs first — a reply containing
    both a digit and a number word ("a dozen, so like 12") should read the
    explicit digit."""
    t = (text or "").strip().lower()
    if not t:
        return None
    m = _NUMERIC_RE.search(t)
    if m:
        try:
            return Decimal(m.group(1))
        except InvalidOperation:
            return None
    for phrase, value in sorted(_NUMBER_WORDS.items(), key=lambda kv: -len(kv[0])):
        if phrase in t:
            return Decimal(value)
    return None
