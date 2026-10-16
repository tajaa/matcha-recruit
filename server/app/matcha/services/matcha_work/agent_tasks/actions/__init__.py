"""Doing something with a finding: buy it, apply to it, book it, write about it.

A playbook names the actions its findings take (`Playbook.actions`); each is
an `ItemAction` (`base.py`) in `ACTIONS`. Every action is proposed first (the
server freezes exactly what it will do and shows it), confirmed by the
person, then carried out once (`service.py`). Adding an action is a module
with an `ACTION` and a line here; nothing else changes (routes, the app,
the chat).
"""
from __future__ import annotations

import re
from typing import get_args

from ..playbook import IntakeType, ItemKind
from . import apply, buy
from .base import ActionContext, ActionError, ItemAction, Line, Proposal, outcome

ACTIONS: dict[str, ItemAction] = {a.key: a for a in (buy.ACTION, apply.ACTION)}
_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")
_ICONS = ("cart", "calendar", "envelope", "link", "phone")


def get(key: str | None) -> ItemAction | None:
    return ACTIONS.get(key or "")


def validate(action: ItemAction) -> None:
    """Raises ValueError naming the first thing wrong with this action."""
    def fail(why: str) -> None:
        raise ValueError(f"action {action.key!r}: {why}")

    if not _KEY.fullmatch(action.key):
        fail("bad key")
    if not action.label.strip() or not action.description.strip() or not action.confirm_label.strip():
        fail("needs a label, a description and a confirm label")
    if action.icon not in _ICONS:
        fail(f"unknown icon {action.icon!r}")
    if not action.item_kinds or any(k not in get_args(ItemKind) for k in action.item_kinds):
        fail("needs item kinds it applies to")
    if action.per_day < 1 or not 1 <= action.proposal_minutes <= 24 * 60:
        fail("bad limits")
    for spec in action.params:
        if not _KEY.fullmatch(spec.key) or spec.type not in get_args(IntakeType) or spec.type in ("file", "consent"):
            fail(f"bad param {spec.key!r}")


for _action in ACTIONS.values():
    validate(_action)

__all__ = ["ACTIONS", "ActionContext", "ActionError", "ItemAction", "Line", "Proposal", "get", "outcome", "validate"]
