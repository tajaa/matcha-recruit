"""Import + route-table smoke for the two sym-link routers. No app boot, no DB.

Imports the modules by their own path (not through `app.matcha.routes`, whose
`__init__` boots the entire router zoo and needs WeasyPrint's native libs).
"""
import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

from tests._helpers.routes import iter_api_routes

SERVER = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    """Load a route module directly, registering a stub `app.matcha.routes`
    package so the module's absolute `app.matcha.routes.ir_incidents._shared`
    import resolves to the real file without running routes/__init__.py."""
    if "app.matcha.routes" not in sys.modules:
        pkg = types.ModuleType("app.matcha.routes")
        pkg.__path__ = [str(SERVER / "app/matcha/routes")]
        sys.modules["app.matcha.routes"] = pkg
    spec = importlib.util.spec_from_file_location(name, SERVER / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def admin_router():
    return _load("app.matcha.routes.symlink", "app/matcha/routes/symlink.py").router


@pytest.fixture(scope="module")
def public_router():
    return _load("app.matcha.routes.intake.symlink_public", "app/matcha/routes/intake/symlink_public.py").router


def _paths(router):
    return {(r.path, tuple(sorted(r.methods))) for r in router.routes}


def test_admin_router_exposes_the_expected_surface(admin_router):
    paths = _paths(admin_router)
    expected = {
        ("/kinds", ("GET",)),
        ("/links", ("GET",)),
        ("/links", ("POST",)),
        ("/links/{link_id}", ("GET",)),
        ("/links/{link_id}/resend", ("POST",)),
        ("/links/{link_id}/revoke", ("POST",)),
        ("/links/{link_id}/attachments/{attachment_id}/download", ("GET",)),
        ("/submissions", ("GET",)),
        ("/submissions/{submission_id}/apply", ("POST",)),
        ("/submissions/{submission_id}/reject", ("POST",)),
        ("/passcode", ("GET",)),
        ("/passcode/rotate", ("POST",)),
        ("/passcode/settings", ("PUT",)),
        ("/channels", ("GET",)),
        ("/employees", ("GET",)),
    }
    assert expected <= paths
    # No empty-path route — the mount owns the prefix.
    assert not any(p == "" for p, _ in paths)


def test_public_router_exposes_the_expected_surface(public_router):
    paths = _paths(public_router)
    expected = {
        ("/sym/{token}", ("GET",)),
        ("/sym/{token}/unlock", ("POST",)),
        ("/sym/{token}/chat/turn", ("POST",)),
        ("/sym/{token}/attachments", ("POST",)),
        ("/sym/{token}/attachments/{attachment_id}", ("DELETE",)),
        ("/sym/{token}/submit", ("POST",)),
    }
    assert expected <= paths


def test_public_gate_reads_raw_flag_with_off_default():
    mod = _load("app.matcha.routes.intake.symlink_public", "app/matcha/routes/intake/symlink_public.py")
    assert mod._symlink_allowed({"symlink": True})
    assert not mod._symlink_allowed({"symlink": False})
    assert not mod._symlink_allowed({})  # default OFF — unlike ir_magic_links
    assert not mod._symlink_allowed({"incidents": True})


def test_feature_flag_is_registered_default_off():
    from app.core.feature_flags import DEFAULT_COMPANY_FEATURES

    assert DEFAULT_COMPANY_FEATURES["symlink"] is False


def test_employee_search_escapes_like_metacharacters(admin_router):
    import sys

    mod = sys.modules["app.matcha.routes.symlink"]
    assert mod._escape_like("50%_a\\b") == "50\\%\\_a\\\\b"
    import inspect

    src = inspect.getsource(mod.search_employees)
    assert src.count("ESCAPE '\\\\'") == 3


def test_merged_features_has_no_silent_fallback(admin_router):
    import inspect
    import sys

    mod = sys.modules["app.matcha.routes.symlink"]
    assert "except TypeError" not in inspect.getsource(mod._merged_features)


def test_passcode_weekday_change_anchors_on_now(admin_router):
    import inspect
    import sys

    src = inspect.getsource(sys.modules["app.matcha.routes.symlink"].update_passcode_settings)
    assert 'next_rotation(row["rotated_at"]' not in src
    assert "next_rotation(datetime.now(timezone.utc)" in src


def _hourly(limit: int, window: int) -> float:
    """A per-IP ceiling normalised to requests/hour so windows are comparable."""
    return limit * 3600 / window


_IP_KEY = re.compile(r"^symlink_(?P<kind>[a-z]+)_ip(?:_hr)?$")


def _public_module():
    return sys.modules["app.matcha.routes.intake.symlink_public"]


def _ip_rates_by_kind(mod) -> dict[str, float]:
    """kind -> its BINDING per-IP rate: the tightest ceiling once every window
    is expressed per hour (a 60/min burst normalises to 3600/hr but can never
    outrun the hourly cap beside it). Every key must parse, so a key named
    outside the scheme can't slip past the invariants below."""
    rates: dict[str, list[float]] = {}
    for key, (limit, window) in mod.IP_LIMITS.items():
        m = _IP_KEY.match(key)
        assert m, f"IP_LIMITS key {key!r} is not symlink_<kind>_ip[_hr]; it would escape every invariant"
        rates.setdefault(m["kind"], []).append(_hourly(limit, window))
    return {kind: min(values) for kind, values in rates.items()}


def test_every_ip_limit_has_a_design_load_and_a_governor(public_router):
    mod = _public_module()
    kinds = set(_ip_rates_by_kind(mod))
    assert kinds == set(mod.PER_RECIPIENT_NEED), "every per-IP kind needs a stated per-recipient load"
    # Every kind is governed per link + per company, except unlock (per link +
    # FAILURES per company — see test_unlock_guessing_is_bounded_per_tenant).
    assert set(mod.LINK_BUDGETS) == kinds - {"unlock"}


def test_structural_needs_track_the_caps_they_come_from(public_router):
    mod = _public_module()
    assert mod.PER_RECIPIENT_NEED["turn"] == mod.chat.MAX_TURNS
    assert mod.PER_RECIPIENT_NEED["upload"] == mod.MAX_ATTACHMENT_SLOTS
    assert mod.PER_RECIPIENT_NEED["delete"] == mod.MAX_ATTACHMENT_SLOTS
    assert mod.PER_RECIPIENT_NEED["submit"] == 1


def test_an_office_behind_one_nat_is_never_throttled_per_ip(public_router):
    """The design load: OFFICE_RECIPIENTS recipients on one NAT address, each
    finishing their whole task within the hour. With MAX_TURNS=20 a 20-person
    office is 400 turns — a 200/hr ceiling 429'd it mid-conversation, and a
    test that only compared per-IP against the per-LINK budget couldn't see it."""
    mod = _public_module()
    for kind, rate in _ip_rates_by_kind(mod).items():
        office = mod.OFFICE_RECIPIENTS * mod.PER_RECIPIENT_NEED[kind]
        assert rate >= office, (
            f"per-IP {kind} allows {rate:.0f}/hr but an office of {mod.OFFICE_RECIPIENTS} needs {office}"
        )


def test_budgets_sit_between_one_recipient_and_the_whole_tenant(public_router):
    mod = _public_module()
    rates = _ip_rates_by_kind(mod)
    for kind, (per_link, per_company) in mod.LINK_BUDGETS.items():
        need, rate = mod.PER_RECIPIENT_NEED[kind], rates[kind]
        assert per_link >= need, f"{kind}: one recipient's task ({need}) doesn't fit its link budget ({per_link})"
        assert per_link < rate, f"{kind}: per-IP ({rate:.0f}/hr) would bind before per-link ({per_link})"
        assert per_company > rate, (
            f"{kind}: one address at the per-IP ceiling ({rate:.0f}/hr) could drain the company ({per_company})"
        )


def test_unlock_guessing_is_bounded_per_tenant(public_router):
    """The passcode is company-wide. Per link bounds one token; per company only
    FAILED attempts count, so an office's typos never lock it out while an
    attacker spreading leaked links across many addresses still gets a fixed
    number of guesses per tenant per hour."""
    mod = _public_module()
    assert "unlock" not in mod.LINK_BUDGETS
    assert mod.UNLOCK_PER_LINK_HOURLY == 12
    rate = _ip_rates_by_kind(mod)["unlock"]
    assert rate > mod.UNLOCK_PER_LINK_HOURLY
    typos = mod.OFFICE_RECIPIENTS * (mod.PER_RECIPIENT_NEED["unlock"] - 1)
    assert mod.UNLOCK_FAILURES_PER_COMPANY_HOURLY >= typos
    # The tenant-wide ceiling is tighter than one address alone would allow.
    assert mod.UNLOCK_FAILURES_PER_COMPANY_HOURLY < rate


def _handler_tree(route):
    import ast
    import inspect
    import textwrap

    return ast.parse(textwrap.dedent(inspect.getsource(route.endpoint))).body[0]


def _first_await(fn):
    import ast

    for stmt in fn.body:  # statements in source order; walk within each
        for node in ast.walk(stmt):
            if isinstance(node, ast.Await):
                return node
    return None


def test_public_handlers_charge_the_ip_limit_before_any_other_work(public_router):
    """Structural, not a substring match: the FIRST await in every public
    handler is `_ip_limit(...)`, and no handler declares a body parameter.
    FastAPI reads File/Form/body-model parameters before the handler runs, so a
    declared UploadFile is spooled whole before any limit can be charged — which
    is what the upload endpoint used to do."""
    import ast

    for route in iter_api_routes(public_router):
        label = f"{sorted(route.methods)} {route.path}"
        assert route.dependant.body_params == [], f"{label} declares a body FastAPI parses before the handler"
        first = _first_await(_handler_tree(route))
        assert first is not None and isinstance(first.value, ast.Call), f"{label} awaits nothing"
        func = first.value.func
        assert isinstance(func, ast.Name) and func.id == "_ip_limit", (
            f"{label}: first await is {ast.unparse(first.value)!r}, not _ip_limit(...)"
        )


def test_every_limit_key_used_exists_and_every_row_is_used(public_router):
    """A key missing from its table used to be a KeyError (a 500 on a public
    route); a row nothing charges is a limit that isn't one."""
    import ast
    import inspect

    mod = _public_module()
    ip_keys: set[str] = set()
    budget_kinds: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(mod))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id == "_ip_limit":
            ip_keys.add(node.args[1].value)
        elif node.func.id == "_budget":
            budget_kinds.add(node.args[2].value)
    assert ip_keys == set(mod.IP_LIMITS)
    assert budget_kinds == set(mod.LINK_BUDGETS)


def test_unknown_limit_key_fails_closed_instead_of_500(public_router, monkeypatch):
    import asyncio

    mod = _public_module()
    calls = []

    async def record(key, action, limit, window):
        calls.append((action, limit, window))

    monkeypatch.setattr(mod, "check_rate_limit", record)
    asyncio.run(mod._ip_limit("198.51.100.7", "symlink_typo_ip"))
    asyncio.run(mod._budget("tok", "co", "typo"))
    assert calls == [
        ("symlink_typo_ip", *mod._UNKNOWN_IP_LIMIT),
        ("symlink_typo_link", mod._UNKNOWN_BUDGET[0], 3600),
        ("symlink_typo_co", mod._UNKNOWN_BUDGET[1], 3600),
    ]


def test_rate_limit_numbers_live_in_the_tables(public_router):
    """No inline magic numbers: `check_rate_limit` is reached through `_ip_limit`
    or `_budget` (which read IP_LIMITS / LINK_BUDGETS), and the direct calls in
    unlock_symlink pass named constants, not literals."""
    import ast
    import inspect

    mod = _public_module()
    tree = ast.parse(inspect.getsource(mod))

    callers: dict[str, list[ast.Call]] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "check_rate_limit"
            ):
                callers.setdefault(fn.name, []).append(node)

    assert set(callers) <= {"_ip_limit", "_budget", "unlock_symlink"}, (
        f"per-IP/per-link limits must go through the tables, not {sorted(set(callers))}"
    )
    for call in callers.get("unlock_symlink", []):
        limit_arg = call.args[2]  # check_rate_limit(key, action, limit, window)
        assert not isinstance(limit_arg, ast.Constant), "unlock limits must be named constants, not literals"


def test_admin_router_is_company_admin_only(admin_router):
    """Sym-link is company-scoped: it needs a tenant, a roster and a company
    passcode. `individual` (personal matcha-work, no company) must not reach it,
    and neither must `employee` — the recipient side is the unauthenticated
    /sym/{token} surface, not this router.

    Asserted against the router object, not the module text: a new endpoint
    added with the wrong dependency, or with none at all, has to fail here.
    """
    import inspect
    import sys

    mod = sys.modules["app.matcha.routes.symlink"]
    gate = mod.require_symlink_admin

    def _guarded(dependant) -> bool:
        return any(
            sub.call is gate or _guarded(sub)
            for sub in dependant.dependencies
        )

    ungated = [
        f"{sorted(route.methods)} {route.path}"
        for route in iter_api_routes(admin_router)
        if not _guarded(route.dependant)
    ]
    assert ungated == [], f"endpoints not behind require_symlink_admin: {ungated}"
    # And the gate is the narrowed one, not the shared dep that also admits `individual`.
    assert "Depends(require_admin_or_client)" not in inspect.getsource(mod)
