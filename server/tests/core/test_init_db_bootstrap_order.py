"""init_db wires the Fractional HR bootstrap where the broker bootstrap used to run."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.database import bootstrap

STEPS = [
    "create_incidents", "create_leads_policies", "create_compliance", "create_jurisdictions",
    "create_portal_chat", "create_data_sources", "create_fractional", "create_provisioning",
    "create_seeds_platform", "create_matcha_work", "create_training", "create_misc_tail",
    "create_ems", "create_inventory",
]


class _Conn:
    def __init__(self, initialized):
        self.initialized = initialized

    async def fetchval(self, *_a, **_k):
        return self.initialized

    async def execute(self, *_a, **_k):
        return "OK"


@pytest.fixture
def calls(monkeypatch):
    order: list[str] = []

    for name in dir(bootstrap):
        if name.startswith("create_"):
            async def _step(_conn, _name=name):
                order.append(_name)
            monkeypatch.setattr(bootstrap, name, _step)

    async def _handbook(_conn):
        order.append("handbook")

    monkeypatch.setattr(bootstrap, "_ensure_handbook_tables", _handbook)
    return order


def _run(monkeypatch, initialized):
    @asynccontextmanager
    async def _get_connection():
        yield _Conn(initialized)

    monkeypatch.setattr(bootstrap, "get_connection", _get_connection)
    asyncio.run(bootstrap.init_db())


def test_fresh_database_runs_every_step_including_fractional(monkeypatch, calls):
    _run(monkeypatch, initialized=False)
    steps = [c for c in calls if c.startswith("create_")]
    assert "create_fractional" in steps
    assert not hasattr(bootstrap, "create_broker")
    assert steps.index("create_data_sources") < steps.index("create_fractional") < steps.index("create_provisioning")
    assert set(STEPS) <= set(steps)


def test_initialized_database_takes_the_fast_path(monkeypatch, calls):
    _run(monkeypatch, initialized=True)
    assert calls == ["handbook"]
