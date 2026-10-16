"""What a kind of task is: what it asks for, what it finds, how it runs.

A `Playbook` is data. The research playbook (`research/`) is the first one;
job search, agent cards and reservations become playbooks as they move into
Tasks. Everything a playbook declares is checked once, at import
(`playbooks.validate_registry`), the way the assistant's ability catalog is.

* `intake`: the facts it may ask the person for (at most 8), each with how to
  ask (`always`, `if_missing`, `never`). Intake forms are built from these and
  nothing else, so the model can only name fields, never invent them.
* `validate_brief`: the server-side check of what came back. Raises
  ValueError with a message the person can read.
* `field_library`: the fields a finding may carry (price, beds, rating...).
  A plan picks from it; a field the library lacks is never stored.
* `phases`: name -> phase function, run by the task chain
  (`orchestrator.TASK_CHAIN`) as `<playbook>.<name>`.
* `round_phases`: where each kind of follow-up round starts.
* `actions`: what its findings can do in the world (buy, book, write):
  keys into `actions.ACTIONS`, each proposed, confirmed, then carried out
  once. (`item_actions` are the person's own marks: save, dismiss, a note.)

What a task costs is `allowance.WEIGHTS[playbook.key]` (and
`allowance.ROUND_UNITS` per follow-up), so every price lives in one table.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Mapping, get_args

IntakeType = Literal[
    "text", "number", "money", "date", "time", "select", "multi_select", "boolean",
    "location", "list", "file", "consent",
]
Ask = Literal["always", "if_missing", "never"]
ItemType = Literal["money", "number", "rating", "text", "date", "bool", "tags"]
Engine = Literal["chain", "job_search", "board"]
RoundKind = Literal["refine", "more", "document", "action"]
ItemKind = Literal["listing", "product", "place", "slot", "flight", "offer", "other"]
FileKind = Literal["document", "image"]

MAX_INTAKE = 14
_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")


@dataclass(frozen=True, kw_only=True)
class IntakeField:
    key: str
    label: str
    type: IntakeType
    required: bool = False
    ask: Ask = "if_missing"
    help: str = ""
    options: tuple[str, ...] = ()
    # file: which kinds it takes, how many, and the most bytes each.
    accept: tuple[FileKind, ...] = ()
    max_count: int = 1
    max_bytes: int = 0
    # What the field starts as in a form ("yes" for a switch that starts on).
    default: str = ""

    def view(self) -> dict:
        out: dict[str, Any] = {
            "key": self.key, "label": self.label, "type": self.type,
            "required": self.required, "ask": self.ask, "help": self.help,
        }
        if self.default:
            out["value"] = self.default
        if self.options:
            out["options"] = list(self.options)
        if self.type == "file":
            out.update(accept=list(self.accept), max_count=self.max_count, max_bytes=self.max_bytes)
        return out


@dataclass(frozen=True, kw_only=True)
class ItemField:
    """One fact a finding can carry, and how it reads."""

    key: str
    label: str
    type: ItemType
    # tags: the values it may hold, value -> label.
    tags: Mapping[str, str] = field(default_factory=dict)
    # The direction a preference on it usually goes: True when more is better.
    higher_is_better: bool | None = None
    help: str = ""

    def view(self) -> dict:
        out: dict[str, Any] = {"key": self.key, "label": self.label, "type": self.type}
        if self.tags:
            out["tags"] = [{"value": k, "label": v} for k, v in self.tags.items()]
        return out


@dataclass(frozen=True, kw_only=True)
class Budgets:
    """Per round, except `items` and `images` (per task)."""

    provider_calls: int = 30
    # An apartment building may take four: its site, its floor plans page
    # and its leasing system (`research/units.py`).
    fetch_calls: int = 160
    browser_views: int = 24  # a building without a rent may take two
    model_runs: int = 8
    items: int = 80
    items_after_more: int = 120
    images: int = 24
    images_per_item: int = 3


PhaseFn = Callable[[dict, Any, Any], Awaitable[Any]]


@dataclass(frozen=True, kw_only=True, eq=False)
class Playbook:
    key: str
    label: str
    # What it is for, in the model's words: when Espresso should pick it.
    description: str
    engine: Engine
    item_kinds: tuple[ItemKind, ...]
    intake: tuple[IntakeField, ...]
    validate_brief: Callable[[dict], dict]
    field_library: Mapping[str, ItemField]
    phases: Mapping[str, PhaseFn]
    first_phase: str
    round_phases: Mapping[RoundKind, str]
    # rerank(conn, task_row): recompute the findings' order from stored facts.
    rerank: Callable[[Any, dict], Awaitable[int]]
    # A plan constraint as the person reads it ("Price at most $3,500").
    describe_constraint: Callable[[dict], str] | None = None
    item_actions: tuple[str, ...] = ()
    # Keys into `actions.ACTIONS`: buy, book, ... for the kinds they fit.
    actions: tuple[str, ...] = ()
    # The disclosure (`agent_runtime/consent.py`) a person agrees to first, if any.
    consent: str | None = None
    # Whether this server can run it (a provider key, the browser worker).
    env_ready: Callable[[], bool] = lambda: True
    budgets: Budgets = Budgets()
    model_surface: str = ""
    personal_only: bool = True
    max_rounds: int = 12
    # Playbooks built on another's phases (the kinds of search on research's)
    # store them under its name, so one phase function has one name.
    phase_prefix: str = ""

    def phase_key(self, name: str) -> str:
        return f"{self.phase_prefix or self.key}.{name}"

    def view(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "item_kinds": list(self.item_kinds),
            "intake": [f.view() for f in self.intake],
            "rounds": sorted(k for k in self.round_phases),
            "item_actions": list(self.item_actions),
            "actions": list(self.actions),
            "consent": self.consent,
            "available": bool(self.env_ready()),
        }

    def validate(self) -> None:
        """Raises ValueError naming the first thing wrong with this playbook."""
        from . import allowance

        def fail(why: str) -> None:
            raise ValueError(f"playbook {self.key!r}: {why}")

        if not _KEY.fullmatch(self.key):
            fail("bad key")
        if self.key not in allowance.WEIGHTS:
            fail("no cost in allowance.WEIGHTS")
        if self.engine not in get_args(Engine):
            fail(f"unknown engine {self.engine!r}")
        if not self.description.strip():
            fail("needs a description")
        if len(self.intake) > MAX_INTAKE:
            fail(f"more than {MAX_INTAKE} intake fields")
        keys = [f.key for f in self.intake]
        if len(set(keys)) != len(keys):
            fail("duplicate intake keys")
        for item in self.intake:
            if not _KEY.fullmatch(item.key) or item.type not in get_args(IntakeType):
                fail(f"bad intake field {item.key!r}")
            if item.type in ("select", "multi_select") and not item.options:
                fail(f"{item.key}: a select needs options")
            if item.type == "file" and (not item.accept or item.max_bytes <= 0 or item.max_count < 1):
                fail(f"{item.key}: a file field needs accept, max_bytes and max_count")
        for key, spec in self.field_library.items():
            if key != spec.key or not _KEY.fullmatch(key) or spec.type not in get_args(ItemType):
                fail(f"bad item field {key!r}")
            if spec.type == "tags" and not spec.tags:
                fail(f"{key}: a tags field needs its values")
        if any(kind not in get_args(ItemKind) for kind in self.item_kinds):
            fail("unknown item kind")
        if self.engine == "chain":
            if self.first_phase not in self.phases:
                fail(f"first phase {self.first_phase!r} is not one of its phases")
            for kind, phase in self.round_phases.items():
                if kind not in get_args(RoundKind) or (kind != "document" and phase not in self.phases):
                    fail(f"round {kind!r} starts at unknown phase {phase!r}")
            for name in self.phases:
                if not _KEY.fullmatch(name):
                    fail(f"bad phase name {name!r}")
            if self.phase_prefix and not _KEY.fullmatch(self.phase_prefix):
                fail("bad phase prefix")
        if self.actions:
            from .actions import ACTIONS

            for key in self.actions:
                action = ACTIONS.get(key)
                if action is None:
                    fail(f"unknown action {key!r}")
                if not set(action.item_kinds) & set(self.item_kinds):
                    fail(f"action {key!r} fits none of its item kinds")
        if self.consent is not None:
            from app.matcha.services.matcha_work.agent_runtime.consent import DISCLOSURES

            if self.consent not in DISCLOSURES:
                fail(f"unknown consent {self.consent!r}")
