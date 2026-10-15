"""The research playbook: go and find things (a home, a product, a place) and keep what fits.

  plan       -> providers -> discover -> enrich -> screen -> rank -> summarize
  (refine)   -> refine -> summarize, or enrich (new facts to check), or
                providers (what's left can't satisfy the change)
  (more)     -> providers -> discover -> ...

See `../CLAUDE.md` for the evidence rules and budgets.
"""
from __future__ import annotations

from app.core.services import agent_surfaces

from ..playbook import Playbook
from . import model_phases, phases, ranking
from .brief import INTAKE, validate_brief
from .fields import LIBRARY

PHASES = {
    "plan": model_phases.plan,
    "providers": phases.run_providers,
    "discover": model_phases.discover,
    "enrich": phases.enrich,
    "screen": model_phases.screen,
    "rank": phases.rank_phase,
    "summarize": model_phases.summarize,
    "refine": model_phases.refine,
}

PLAYBOOK = Playbook(
    key="research",
    label="Research",
    description=(
        "Go and find specific things that fit what the person wants, and keep them as a ranked "
        "list with the evidence for each fact: a home to rent or buy, a product to buy, a "
        "restaurant or other place, an event, a service. Not for job searches or bookings."
    ),
    engine="chain",
    item_kinds=("listing", "product", "place", "offer", "other"),
    intake=INTAKE,
    validate_brief=validate_brief,
    field_library=LIBRARY,
    phases=PHASES,
    first_phase="plan",
    round_phases={"refine": "refine", "more": "providers", "document": "document"},
    rerank=phases.rerank,
    describe_constraint=ranking.describe,
    item_actions=("save", "dismiss", "note", "more_like_this"),
    actions=("buy",),
    budgets=phases.BUDGETS,
    model_surface=agent_surfaces.ESPRESSO_TASKS,
    personal_only=True,
)
