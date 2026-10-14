"""Every playbook, checked once at import.

A new kind of task is an entry here (and a weight in `allowance.WEIGHTS`), not
a branch in the engine.
"""
from __future__ import annotations

from typing import Mapping

from .playbook import PhaseFn, Playbook
from .research import PLAYBOOK as RESEARCH

PLAYBOOKS: Mapping[str, Playbook] = {p.key: p for p in (RESEARCH,)}


def get(key: str | None) -> Playbook | None:
    return PLAYBOOKS.get(key or "")


def chain_phases() -> dict[str, PhaseFn]:
    """Every chain playbook's phases, under the names the task row stores."""
    return {
        playbook.phase_key(name): fn
        for playbook in PLAYBOOKS.values() if playbook.engine == "chain"
        for name, fn in playbook.phases.items()
    }


def validate_registry(playbooks: Mapping[str, Playbook] = PLAYBOOKS) -> None:
    for key, playbook in playbooks.items():
        if key != playbook.key:
            raise ValueError(f"playbook registered as {key!r} is {playbook.key!r}")
        playbook.validate()


validate_registry()
