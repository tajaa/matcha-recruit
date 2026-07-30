"""The setup-concierge agent loop, driven by a scripted fake Gemini — same
harness shape as test_merlin_agent.py (the page editor's loop), asserting the
LOOP's contract rather than model behavior:

  - stage_action validates+gates for real and, on success, persists a
    'proposed' entry and emits a `staged_action` frame the model can see;
  - execute_staged_action refuses an id staged earlier in the SAME turn
    (confirm-first, structurally) but proceeds for one staged on a prior turn;
  - finish's `links` are filtered to the target whitelist;
  - the model-call bound force-finishes rather than running away;
  - exactly one `result` frame is emitted, always, last;
  - RateLimitExceeded is the one exception that escapes.

DB access (`get_connection`, `merlin_store.mutate_staged_actions`,
`merlin_store.get_owned_conversation`, `resolve_entitlements`,
`execute_setup_action`, `compute_readiness`) is faked with a small in-memory
staged-actions list — `evaluate_setup_stage`/`evaluate_setup_execute`
themselves run for REAL (pure, already covered by
test_merlin_setup_actions.py), so these tests also exercise the actual gate
wiring, not just the loop shape.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_setup_agent.py -q
"""
import asyncio
import os
from typing import Any
from uuid import uuid4

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.entitlements import Entitlements  # noqa: E402
from app.cappe.services.merlin import setup_agent  # noqa: E402
from app.cappe.services.merlin.setup_agent import run_setup_agent  # noqa: E402
from app.cappe.services.merlin.setup_actions import new_staged_entry  # noqa: E402

FREE = Entitlements(
    plan_code="free", plan_name="Free", can_sell=True, platform_fee_bps=200,
    allowed_fulfillment=frozenset({"physical", "digital", "service", "booking"}),
    site_limit=1, mailbox_quota_included=0, features={},
)
CREATOR = Entitlements(
    plan_code="creator", plan_name="Creator", can_sell=True, platform_fee_bps=300,
    allowed_fulfillment=frozenset({"service", "booking"}),
    site_limit=None, mailbox_quota_included=0, features={"rider": True},
)

_CONVERSATION_ID = uuid4()
_SITE = {"id": uuid4(), "name": "Demo Site"}


class _FakeAccount:
    def __init__(self, plan="free"):
        self.id = uuid4()
        self.plan = plan
        self.name = "Sam"
        self.account_type = "personal"


_CONTEXT = {
    "site_name": "Demo Site", "account_name": "Sam", "account_type": "personal",
    "plan": "free", "plan_name": "Free", "allowed_fulfillment": ["physical", "digital", "service", "booking"],
    "is_premium": False, "readiness": {"ready": False, "items": []},
    "pages": [], "products": [], "product_count": 0, "booking_type_count": 0,
    "subscriber_count": 0, "promo_bar_enabled": False, "promo_popup_enabled": False,
}


# --- fakes (Gemini side, identical shape to test_merlin_agent.py) -----------

class _FakeCall:
    def __init__(self, name: str, args: dict[str, Any]):
        self.name = name
        self.args = args


class _FakePart:
    def __init__(self, call: _FakeCall):
        self.function_call = call


class _FakeContent:
    def __init__(self, parts):
        self.parts = parts


class _FakeCandidate:
    def __init__(self, calls):
        self.content = _FakeContent([_FakePart(c) for c in calls])


class _FakeResponse:
    def __init__(self, calls, text=""):
        self.candidates = [_FakeCandidate(calls)]
        self.text = text


class _FakeModels:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def generate_content(self, **kwargs):
        self.calls += 1
        if not self.script:
            return _FakeResponse([], text="ran out of script")
        turn = self.script.pop(0)
        if isinstance(turn, str):
            return _FakeResponse([], text=turn)
        return _FakeResponse([_FakeCall(name, args) for name, args in turn])


class _FakeClient:
    def __init__(self, script):
        self.aio = type("aio", (), {"models": _FakeModels(script)})()


class _NoopLimiter:
    async def check_limit(self, *_a, **_k):
        return None

    async def record_call(self, *_a, **_k):
        return None


# --- fakes (DB side) ----------------------------------------------------------

class _FakeTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False


class _FakeConnHandle:
    """Everything DB-shaped this loop touches is monkeypatched at the
    `merlin_store`/`resolve_entitlements`/etc. level, so this handle only
    needs to satisfy `async with get_connection() as conn, conn.transaction():`
    — the row-locked-transaction shape `do_execute_staged_action` now uses."""

    def transaction(self):
        return _FakeTxn()


class _FakeConnCtx:
    async def __aenter__(self):
        return _FakeConnHandle()

    async def __aexit__(self, *_a):
        return False


@pytest.fixture
def patched(monkeypatch):
    """Backs the staged-actions store with an in-memory list, and returns a
    helper that runs a whole turn and collects its frames. The in-memory
    store is closed over by this fixture, so multiple `_run` calls in one
    test share it — useful for a "prior turn already staged this" setup."""
    store: dict[str, list[dict[str, Any]]] = {"actions": []}
    entitlements_by_plan = {"free": FREE, "creator": CREATOR}

    async def _fake_mutate(conn, conversation_id, fn):
        store["actions"] = fn(store["actions"])
        return store["actions"]

    async def _fake_get_owned_conversation(conn, conversation_id, account_id):
        return {"staged_actions": store["actions"]}

    async def _fake_lock_conversation_actions(conn, conversation_id):
        return store["actions"]

    async def _fake_resolve_entitlements(plan, *, conn=None):
        return entitlements_by_plan.get(plan, FREE)

    async def _fake_execute_setup_action(conn, site, account, entry):
        return {
            "ok": True, "status": "executed", "result": {"id": "created-1"},
            "message": f"Done — {entry['summary']}.",
        }

    async def _fake_compute_readiness(conn, site_id, site):
        return {"ready": False, "items": []}

    monkeypatch.setattr(setup_agent, "get_connection", lambda: _FakeConnCtx())
    monkeypatch.setattr(setup_agent.merlin_store, "mutate_staged_actions", _fake_mutate)
    monkeypatch.setattr(setup_agent.merlin_store, "get_owned_conversation", _fake_get_owned_conversation)
    monkeypatch.setattr(setup_agent.merlin_store, "lock_conversation_actions", _fake_lock_conversation_actions)
    monkeypatch.setattr(setup_agent, "resolve_entitlements", _fake_resolve_entitlements)
    monkeypatch.setattr(setup_agent, "execute_setup_action", _fake_execute_setup_action)
    monkeypatch.setattr(setup_agent, "compute_readiness", _fake_compute_readiness)
    monkeypatch.setattr(setup_agent, "invalidate_site_render_cache", lambda *_a, **_k: asyncio.sleep(0))
    monkeypatch.setattr(setup_agent, "GeminiRateLimiter", lambda: _NoopLimiter())

    def _run(script, *, preexisting=None, account=None, **overrides):
        if preexisting is not None:
            store["actions"] = list(preexisting)
        fake = _FakeClient(script)
        monkeypatch.setattr(setup_agent, "get_genai_client", lambda *a, **k: fake)

        kwargs = {
            "message": "help me set up my site",
            "history": [],
            "context": _CONTEXT,
            "site": _SITE,
            "account": account or _FakeAccount(),
            "conversation_id": _CONVERSATION_ID,
        }
        kwargs.update(overrides)

        async def _collect():
            return [f async for f in run_setup_agent(**kwargs)]

        frames = asyncio.run(_collect())
        return frames, fake.aio.models, store

    _run.store = store
    return _run


def _result(frames):
    results = [f for f in frames if f["type"] == "result"]
    assert len(results) == 1, "exactly one result frame, always"
    assert frames[-1]["type"] == "result", "the result frame is last"
    return results[0]["data"]


# --- tests ---------------------------------------------------------------

def test_stage_action_emits_a_staged_action_frame(patched):
    frames, models, store = patched([
        [("stage_action", {"type": "create_page", "payload": '{"title":"About Us","preset":"about"}'})],
        [("finish", {"message": "I've staged an About page for you."})],
    ])
    data = _result(frames)

    staged_frames = [f for f in frames if f["type"] == "staged_action"]
    assert len(staged_frames) == 1
    assert staged_frames[0]["action"]["type"] == "create_page"
    assert staged_frames[0]["action"]["status"] == "proposed"
    assert len(store["actions"]) == 1
    assert data["message"] == "I've staged an About page for you."


def test_stage_action_never_writes_when_the_gate_blocks(patched):
    """A digital product this plan's entitlements block must not be staged —
    the model is told why, and nothing lands in the queue."""
    frames, _, store = patched(
        [
            [("stage_action", {
                "type": "create_product",
                "payload": '{"name":"Ebook","fulfillment":"digital","price_cents":500}',
            })],
            [("finish", {"message": "Handled."})],
        ],
        account=_FakeAccount(plan="creator"),
    )

    assert not [f for f in frames if f["type"] == "staged_action"]
    assert store["actions"] == []


def test_confirm_first_refuses_an_id_staged_this_same_turn(patched, monkeypatch):
    """The realistic shape: turn 1 stages, turn 2 (still ONE run_setup_agent
    call — `staged_this_turn` is scoped to the whole call) tries to confirm
    the id it was just handed. `new_staged_entry` is pinned to a known id so
    the script can name it without a live round-trip to discover it."""
    from app.cappe.services.merlin import setup_actions as sa

    def _fixed_entry(action_type, payload, summary):
        return {
            "id": "fixed-1", "type": action_type, "summary": summary, "payload": payload,
            "status": "proposed", "result": None, "message": None,
            "created_at": "2026-01-01T00:00:00+00:00", "executed_at": None,
        }

    monkeypatch.setattr(setup_agent, "new_staged_entry", _fixed_entry)

    frames, models, store = patched([
        [("stage_action", {"type": "create_page", "payload": '{"title":"About Us","preset":"about"}'})],
        [("execute_staged_action", {"action_id": "fixed-1"})],
        [("finish", {"message": "Done."})],
    ])

    staged_frames = [f for f in frames if f["type"] == "staged_action"]
    # The refused confirm touches nothing — do_execute_staged_action returns
    # no entry on refusal, so there is no second card update, only the one
    # from the original stage.
    assert len(staged_frames) == 1
    assert staged_frames[0]["action"]["status"] == "proposed"
    assert store["actions"][0]["status"] == "proposed", "a same-turn confirm must not flip it to executed"
    data = _result(frames)
    assert any("same turn" in r["summary"] or "confirm it on a later message" in r["summary"] for r in data["results"]), (
        data["results"]
    )


def test_execute_proceeds_for_an_action_staged_on_a_prior_turn(patched):
    preexisting = [new_staged_entry(
        "create_page", {"title": "About Us", "preset": "about", "blocks": None}, "Create About Us",
    )]
    action_id = preexisting[0]["id"]

    frames, _, store = patched([
        [("execute_staged_action", {"action_id": action_id})],
        [("finish", {"message": "Done."})],
    ], preexisting=preexisting)

    staged = [f for f in frames if f["type"] == "staged_action"]
    assert staged, "an executed entry still emits a staged_action frame with its new status"
    assert staged[-1]["action"]["status"] == "executed"
    assert store["actions"][0]["status"] == "executed"


def test_execute_refuses_an_already_executed_action(patched):
    """Idempotency: a second confirm attempt against a settled entry refuses
    rather than re-running the write."""
    preexisting = [new_staged_entry("create_page", {"title": "X", "preset": "about", "blocks": None}, "s")]
    preexisting[0]["status"] = "executed"
    action_id = preexisting[0]["id"]

    frames, _, store = patched([
        [("execute_staged_action", {"action_id": action_id})],
        [("finish", {"message": "Done."})],
    ], preexisting=preexisting)

    assert not [f for f in frames if f["type"] == "staged_action"], (
        "an already-settled entry produces no new card update"
    )
    assert store["actions"][0]["status"] == "executed"


def test_finish_links_are_filtered_to_the_whitelist(patched):
    frames, _, _ = patched([
        [("finish", {
            "message": "Here's what's next.",
            "links": [
                {"target": "shop", "label": "Open Shop"},
                {"target": "javascript:alert(1)", "label": "evil"},
                {"target": "page:abc-123", "label": "Open the page"},
            ],
        })],
    ])
    data = _result(frames)
    targets = {link["target"] for link in data["links"]}
    assert targets == {"shop", "page:abc-123"}


def test_model_call_bound_forces_a_finish(patched):
    stage_turn = [("stage_action", {"type": "create_page", "payload": '{"title":"X","preset":"about"}'})]
    frames, models, _ = patched([stage_turn] * 20)
    data = _result(frames)

    assert models.calls == setup_agent._MODEL_CALLS
    assert data["message"]


def test_a_model_error_still_yields_a_result_frame(patched, monkeypatch):
    class _Boom:
        async def generate_content(self, **_kw):
            raise RuntimeError("gemini is down")

    class _BoomClient:
        def __init__(self):
            self.aio = type("aio", (), {"models": _Boom()})()

    monkeypatch.setattr(setup_agent, "get_genai_client", lambda *a, **k: _BoomClient())

    async def _collect():
        return [
            f async for f in run_setup_agent(
                message="hi", history=[], context=_CONTEXT, site=_SITE,
                account=_FakeAccount(), conversation_id=_CONVERSATION_ID,
            )
        ]

    frames = asyncio.run(_collect())
    assert any(f["type"] == "error" for f in frames)
    data = _result(frames)
    assert data["results"] == []


def test_rate_limit_propagates(patched, monkeypatch):
    from app.core.services.rate_limiter import RateLimitExceeded

    class _Limited:
        async def check_limit(self, *_a, **_k):
            raise RateLimitExceeded("cap reached", "daily", 100, 100)

        async def record_call(self, *_a, **_k):
            return None

    monkeypatch.setattr(setup_agent, "get_genai_client", lambda *a, **k: _FakeClient([]))
    monkeypatch.setattr(setup_agent, "GeminiRateLimiter", lambda: _Limited())

    async def _collect():
        return [
            f async for f in run_setup_agent(
                message="hi", history=[], context=_CONTEXT, site=_SITE,
                account=_FakeAccount(), conversation_id=_CONVERSATION_ID,
            )
        ]

    with pytest.raises(RateLimitExceeded):
        asyncio.run(_collect())


def test_a_prose_turn_ends_the_loop_as_the_message(patched):
    frames, models, _ = patched(["I can help — what would you like to set up first?"])
    data = _result(frames)
    assert data["message"] == "I can help — what would you like to set up first?"
    assert models.calls == 1
