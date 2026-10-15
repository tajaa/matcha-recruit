"""Every playbook, checked once at import.

A new kind of task is an entry here (and a weight in `allowance.WEIGHTS`), not
a branch in the engine.
"""
from __future__ import annotations

from typing import Mapping

from .job_tasks import PLAYBOOK as JOB_SEARCH
from .playbook import PhaseFn, Playbook
from .research import PLAYBOOK as RESEARCH

PLAYBOOKS: Mapping[str, Playbook] = {p.key: p for p in (RESEARCH, JOB_SEARCH)}
# What Espresso can start from chat or a form: its own chains, and job
# searches (which run on their own engine).
STARTABLE_ENGINES = ("chain", "job_search")


def get(key: str | None) -> Playbook | None:
    return PLAYBOOKS.get(key or "")


def startable(playbook: Playbook | None) -> bool:
    return playbook is not None and playbook.engine in STARTABLE_ENGINES and bool(playbook.env_ready())


def startable_keys() -> list[str]:
    """For a tool's enum: every playbook that can be started, ready here or not."""
    return sorted(k for k, p in PLAYBOOKS.items() if p.engine in STARTABLE_ENGINES)


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
