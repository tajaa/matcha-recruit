"""What an action on a finding is.

An `ItemAction` is data plus three functions:

* `available(ctx)`: why it can't be done for this finding (shown on the
  button), or None.
* `prepare(ctx, params)`: what exactly would happen, frozen, and how it reads
  (`Proposal`). Nothing is done yet. Everything in it comes from the stored
  finding and the person's own saved details, never from a model.
* `perform(ctx, frozen)`: do it, from the frozen proposal alone, after the
  person confirmed. Returns what came of it (`outcome()`: a headline, lines,
  and a link the app opens, if any).

The service (`service.py`) owns the rest: who may, how often, the proposal's
lifetime, claiming it once, recording what came of it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from ..playbook import IntakeField, ItemKind

# What the button shows; each app maps these to its own icons.
Icon = Literal["cart", "calendar", "envelope", "link", "phone"]


class ActionError(ValueError):
    """User-facing: why this action can't go ahead (`code` is the HTTP status)."""

    def __init__(self, message: str, code: int = 409):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ActionContext:
    user: Any  # the person (`id`, `email`, `role`)
    task: dict  # the task row
    item: dict  # the finding row


@dataclass(frozen=True)
class Line:
    label: str
    value: str

    def view(self) -> dict:
        return {"label": self.label, "value": self.value}


@dataclass(frozen=True)
class Proposal:
    """What would happen: `frozen` is all `perform` gets; the rest is shown."""

    frozen: dict
    title: str
    lines: tuple[Line, ...] = ()
    note: str = ""
    # The button's words when they differ from the action's `confirm_label`.
    confirm: str = ""

    def preview(self) -> dict:
        return {"title": self.title, "lines": [line.view() for line in self.lines], "note": self.note}


@dataclass(frozen=True, kw_only=True, eq=False)
class ItemAction:
    key: str
    label: str
    icon: Icon
    # What it does, in a sentence the person reads before going ahead.
    description: str
    item_kinds: tuple[ItemKind, ...]
    available: Callable[[ActionContext], str | None]
    prepare: Callable[[ActionContext, dict], Awaitable[Proposal]]
    perform: Callable[[ActionContext, dict], Awaitable[dict]]
    params: tuple[IntakeField, ...] = ()
    confirm_label: str = "Go ahead"
    # Carried out per person per day, at most.
    per_day: int = 20
    # How long a proposal can wait for its yes.
    proposal_minutes: int = 30

    def view(self, ctx: ActionContext | None = None) -> dict:
        reason = self.available(ctx) if ctx is not None else None
        return {
            "key": self.key,
            "label": self.label,
            "icon": self.icon,
            "description": self.description,
            "confirm_label": self.confirm_label,
            "params": [p.view() for p in self.params],
            "available": reason is None,
            "reason": reason,
        }


def outcome(headline: str, lines: tuple[Line, ...] = (), url: str | None = None) -> dict:
    """What `perform` returns, and what the app shows after."""
    return {"headline": headline, "lines": [line.view() for line in lines], "url": url}
