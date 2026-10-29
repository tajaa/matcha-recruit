"""The AI-models registry and the call sites that read it.

    cd server && ./venv/bin/python -m pytest tests/core/test_agent_surfaces.py -q

The admin page, the PUT and every router read one registry
(`core/services/agent_surfaces.py`). These tests keep the code honest about
it: every `claude_override` and `generate_content_routed` call names a
surface, every `agent_surfaces.X` a call site uses exists, and every
registered surface is used somewhere (no dead rows on the admin page).
"""

import ast
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.services import agent_surfaces as reg
from app.matcha.services.matcha_work import app_surface

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _calls(name: str):
    """(path, ast.Call) for every call to `name` (bare or as an attribute) under app/."""
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if called == name:
                yield path, node


def _rel(path: Path) -> str:
    return str(path.relative_to(APP_DIR.parent))


# --- The registry --------------------------------------------------------------

def test_registry_keys_are_unique_and_prefixed_by_their_app():
    keys = [s.key for s in reg.SURFACES]
    assert len(keys) == len(set(keys))
    for surface in reg.SURFACES:
        assert surface.app in reg.APP_KEYS
        assert surface.key.startswith(f"{surface.app}.")
        assert reg.app_of(surface.key) == surface.app


def test_choices_line_up_with_the_claude_models():
    from app.core.services.anthropic_messages import CLAUDE_MODELS

    assert set(reg.CLAUDE_CHOICES) == set(CLAUDE_MODELS)
    assert reg.INHERIT not in reg.MODEL_CHOICES


def test_registry_payload_lists_every_app_and_its_rows_in_order():
    payload = {app["key"]: app for app in reg.registry_payload()}
    assert list(payload) == [app.key for app in reg.APPS]
    for app in reg.APPS:
        rows = [s.key for s in reg.SURFACES if s.app == app.key]
        assert [s["key"] for s in payload[app.key]["surfaces"]] == rows
        assert rows, f"{app.key} has no product rows"
    assert [s["key"] for s in payload[reg.ESPRESSO]["surfaces"]] == [
        reg.ESPRESSO_CHAT, reg.ESPRESSO_AGENT_CARDS, reg.ESPRESSO_ASSISTANT, reg.ESPRESSO_PROJECTS,
        reg.ESPRESSO_JOB_SEARCH, reg.ESPRESSO_TASKS,
    ]
    assert all({"key", "label", "description", "builtin"} <= set(s) for s in payload[reg.MATCHA]["surfaces"])


# --- Call sites ------------------------------------------------------------------

def test_every_claude_override_call_names_a_surface():
    calls = [*_calls("claude_override"), *_calls("claude_default")]
    bare = [_rel(p) for p, call in calls if not call.args and not call.keywords]
    assert bare == [], f"claude_override()/claude_default() with no surface: {bare}"


@pytest.mark.asyncio
async def test_claude_default_is_haiku_with_a_key_and_none_without(monkeypatch):
    from unittest.mock import AsyncMock

    from app.core.services import anthropic_messages as am

    override = AsyncMock(return_value=None)
    monkeypatch.setattr(am, "claude_override", override)
    monkeypatch.setattr(am, "anthropic_configured", lambda: True)
    assert await am.claude_default(reg.ESPRESSO_TASKS) == am.CLAUDE_HAIKU
    # A surface built on another Claude (Merlin in the Studio: Sonnet) names it.
    assert await am.claude_default(reg.GUMMFIT_STUDIO_MERLIN, builtin=am.CLAUDE_SONNET) == am.CLAUDE_SONNET
    override.return_value = am.CLAUDE_HAIKU
    assert await am.claude_default(reg.GUMMFIT_STUDIO_MERLIN, builtin=am.CLAUDE_SONNET) == am.CLAUDE_HAIKU
    override.return_value = am.CLAUDE_SONNET
    assert await am.claude_default(reg.ESPRESSO_TASKS) == am.CLAUDE_SONNET
    override.return_value = None
    monkeypatch.setattr(am, "anthropic_configured", lambda: False)
    assert await am.claude_default(reg.ESPRESSO_TASKS) is None  # the caller's Luna path
    override.assert_awaited_with(reg.ESPRESSO_TASKS)


def test_no_surface_offers_luna_as_its_default():
    assert not [s.key for s in reg.SURFACES if "Luna" in s.builtin]


# Call sites that hand a `surface` parameter straight on; their callers name it.
_PASS_THROUGH = {"app/core/services/anthropic_messages.py", "app/matcha/services/precedent_common.py"}


def _surfaces_named(node: ast.AST, assigned: dict[str, list[ast.AST]]) -> set[str]:
    """The surface keys an argument can be: `agent_surfaces.X`, a
    `work_surface(company, "<product>")` (either app), or a local name
    assigned from those (`key = A if schedule else B`)."""
    keys: set[str] = set()
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                and sub.value.id in {"agent_surfaces", "reg"} and sub.attr.isupper()):
            keys.add(getattr(reg, sub.attr))
        elif (isinstance(sub, ast.Call) and getattr(sub.func, "id", getattr(sub.func, "attr", None)) == "work_surface"
              and len(sub.args) > 1 and isinstance(sub.args[1], ast.Constant)):
            keys |= {app_surface._BUSINESS[sub.args[1].value], app_surface._PERSONAL[sub.args[1].value]}
        elif isinstance(sub, ast.Name) and sub.id in assigned:
            for value in assigned[sub.id]:
                keys |= _surfaces_named(value, {})
    return keys


def _surfaces_by_resolver() -> tuple[set[str], set[str], set[str], list[str]]:
    """(surfaces some call site reads with `claude_default`/`surface_model`,
    those of them whose `claude_default` names Sonnet as its `builtin`,
    surfaces read with `claude_override` or `generate_content_routed`, call
    sites whose surface couldn't be worked out)."""
    haiku, sonnet, gemini, unresolved = set(), set(), set(), []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        assigned: dict[str, list[ast.AST]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.setdefault(target.id, []).append(node.value)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if called in {"claude_default", "surface_model"}:
                builtin = [k.value for k in node.keywords if k.arg == "builtin"]
                own = bool(builtin) and getattr(builtin[0], "attr", None) == "CLAUDE_SONNET"
                into, args = sonnet if own else haiku, node.args[:1]
            elif called == "claude_override":
                into, args = gemini, node.args[:1]
            elif called == "generate_content_routed":
                into, args = gemini, [k.value for k in node.keywords if k.arg == "surface"]
            else:
                continue
            keys = _surfaces_named(args[0], assigned) if args else set()
            if not keys and _rel(path) not in _PASS_THROUGH:
                unresolved.append(f"{_rel(path)}:{node.lineno}")
            into |= keys
    return haiku, sonnet, gemini, unresolved


def test_each_surfaces_label_names_the_providers_its_code_runs():
    """The admin page's "default runs on" text against the code: a surface
    read by `claude_default` runs Claude Haiku by default (Sonnet when it
    passes `builtin=CLAUDE_SONNET`), one read by `claude_override` runs
    Gemini, and a label names exactly those."""
    haiku, sonnet, gemini, unresolved = _surfaces_by_resolver()
    assert unresolved == [], f"a call site's surface could not be worked out: {unresolved}"
    assert sonnet, "the Sonnet branch found no call site (Merlin in the Studio has one)"
    for surface in reg.SURFACES:
        says_haiku, says_gemini = "Claude Haiku" in surface.builtin, "Gemini" in surface.builtin
        says_sonnet = "Claude Sonnet" in surface.builtin
        assert says_haiku == (surface.key in haiku), f"{surface.key}: {surface.builtin!r}"
        assert says_sonnet == (surface.key in sonnet), f"{surface.key}: {surface.builtin!r}"
        assert says_gemini == (surface.key in gemini), f"{surface.key}: {surface.builtin!r}"


def test_every_routed_gemini_call_names_its_surface():
    missing = [
        f"{_rel(p)}:{call.lineno}"
        for p, call in _calls("generate_content_routed")
        if not any(k.arg == "surface" for k in call.keywords)
    ]
    assert missing == [], f"generate_content_routed without surface=: {missing}"


def _constants_used() -> dict[str, list[str]]:
    used: dict[str, list[str]] = {}
    for path in APP_DIR.rglob("*.py"):
        if path.name == "agent_surfaces.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in {"agent_surfaces", "reg"}
                and node.attr.isupper()
            ):
                used.setdefault(node.attr, []).append(_rel(path))
    return used


def test_every_surface_constant_a_call_site_uses_exists():
    unknown = {name: where for name, where in _constants_used().items() if not hasattr(reg, name)}
    assert unknown == {}


def test_every_registered_surface_is_used_by_some_call_site():
    used_keys = {getattr(reg, name) for name in _constants_used() if isinstance(getattr(reg, name, None), str)}
    dead = [s.key for s in reg.SURFACES if s.key not in used_keys]
    assert dead == [], f"registered but never routed (a dead admin row): {dead}"


# --- Matcha Work vs Espresso ------------------------------------------------------

class _Conn:
    def __init__(self, personal):
        self.personal = personal
        self.reads = 0

    async def fetchval(self, query, company_id):
        self.reads += 1
        if isinstance(self.personal, BaseException):
            raise self.personal
        return self.personal


@pytest.fixture
def companies(monkeypatch):
    app_surface._personal.clear()

    def use(personal) -> _Conn:
        conn = _Conn(personal)

        @asynccontextmanager
        async def connection():
            yield conn

        monkeypatch.setattr(app_surface, "connection_or_direct", connection)
        return conn

    yield use
    app_surface._personal.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("product, business, personal", [
    ("chat", reg.MATCHA_WORK_CHAT, reg.ESPRESSO_CHAT),
    ("agent_cards", reg.MATCHA_WORK_AGENT_CARDS, reg.ESPRESSO_AGENT_CARDS),
    ("projects", reg.MATCHA_WORK_PROJECTS, reg.ESPRESSO_PROJECTS),
])
async def test_work_surface_splits_business_from_personal(companies, product, business, personal):
    companies(False)
    assert await app_surface.work_surface(uuid4(), product) == business
    app_surface._personal.clear()
    companies(True)
    assert await app_surface.work_surface(uuid4(), product) == personal


@pytest.mark.asyncio
async def test_personal_flag_is_cached_per_company(companies):
    conn = companies(True)
    company = uuid4()
    await app_surface.work_surface(company, "chat")
    await app_surface.work_surface(str(company), "projects")
    assert conn.reads == 1


@pytest.mark.asyncio
async def test_no_company_or_an_unreadable_flag_is_matcha_work(companies):
    conn = companies(True)
    assert await app_surface.work_surface(None, "chat") == reg.MATCHA_WORK_CHAT
    assert conn.reads == 0
    companies(OSError("db down"))
    assert await app_surface.work_surface(uuid4(), "chat") == reg.MATCHA_WORK_CHAT


@pytest.mark.asyncio
async def test_an_entry_expiring_mid_read_cannot_fail_the_turn(companies, monkeypatch):
    """`in` then `[]` straddling a TTL expiry used to raise KeyError outside the
    try; one `.get` read falls through to the lookup instead."""

    class _Expiring(dict):
        def __contains__(self, key):
            return True  # looks cached…

        def __getitem__(self, key):
            raise KeyError(key)  # …but expired by the time it is read

    conn = companies(True)
    monkeypatch.setattr(app_surface, "_personal", _Expiring())
    assert await app_surface.work_surface(uuid4(), "chat") == reg.ESPRESSO_CHAT
    assert conn.reads == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("personal, surface", [(True, reg.ESPRESSO_CHAT), (False, reg.MATCHA_HANDBOOKS)])
async def test_handbook_upload_check_follows_the_account(monkeypatch, personal, surface):
    from types import SimpleNamespace

    from app.matcha.services.matcha_work import matcha_work_handbook_upload as upload

    seen = {}

    async def routed(client, **kwargs):
        seen["surface"] = kwargs["surface"]
        return SimpleNamespace(text='{"is_handbook": true}')

    async def is_personal(company_id):
        return personal

    monkeypatch.setattr(upload, "_keyword_relevance_check", lambda text: (None, None))
    monkeypatch.setattr(upload, "generate_content_routed", routed)
    monkeypatch.setattr(app_surface, "is_personal_company", is_personal)
    assert await upload.check_handbook_relevance("Our policies", object(), company_id=uuid4()) == (True, None)
    assert seen["surface"] == surface
