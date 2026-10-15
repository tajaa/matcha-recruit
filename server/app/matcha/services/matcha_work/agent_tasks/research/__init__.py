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
from . import kinds, model_phases, phases, ranking
from .brief import INTAKE, validate_brief, validator
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
        "list with the evidence for each fact: an event, a service, a home to buy, anything the "
        "other kinds don't cover. Products, homes to rent and places to go have their own "
        "playbooks (products, apartments, places); job searches too."
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


def kind_playbook(kind: kinds.SearchKind) -> Playbook:
    """A kind of search as a playbook: research's phases, under research's phase
    names, with the kind's own questions, check, facts and actions."""
    return Playbook(
        key=kind.key,
        label=kind.label,
        description=kind.description,
        engine="chain",
        item_kinds=(kind.item_kind,),
        intake=kind.intake,
        validate_brief=validator(kind.brief_model),
        field_library=LIBRARY,
        phases=PHASES,
        first_phase="plan",
        round_phases=PLAYBOOK.round_phases,
        rerank=phases.rerank,
        describe_constraint=ranking.describe,
        item_actions=PLAYBOOK.item_actions,
        actions=kind.actions,
        budgets=phases.BUDGETS,
        model_surface=agent_surfaces.ESPRESSO_TASKS,
        personal_only=True,
        phase_prefix=PLAYBOOK.key,
    )


KIND_PLAYBOOKS = tuple(kind_playbook(kind) for kind in kinds.KINDS.values())
