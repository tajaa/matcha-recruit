"""Import + route-table smoke for the two sym-link routers. No app boot, no DB.

Imports the modules by their own path (not through `app.matcha.routes`, whose
`__init__` boots the entire router zoo and needs WeasyPrint's native libs).
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

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


def _effective_hourly(mod, kind: str) -> float:
    """The binding per-IP rate for a kind: the tightest of its ceilings once
    every window is expressed per hour. A 30/60s burst cap normalises to
    1800/hr but can never outrun the 200/hr cap sitting beside it."""
    rates = [
        _hourly(limit, window)
        for key, (limit, window) in mod.IP_LIMITS.items()
        if key.startswith(f"symlink_{kind}_ip")
    ]
    assert rates, f"no per-IP limit for {kind}"
    return min(rates)


def test_per_ip_limits_are_a_flood_backstop_not_the_binding_constraint(public_router):
    """Per-link/per-company budgets are the cost governors; per-IP is a flood
    backstop. A bulk send puts a whole office behind one NAT address, so a
    per-IP ceiling below the matching per-link budget 429s legitimate
    recipients, and one above the per-company budget lets a single address
    exhaust the tenant's whole hour. Every window is normalised before the
    comparison — the burst caps are part of the invariant, not exempt from it.
    See services/symlink/CLAUDE.md.
    """
    import sys

    mod = sys.modules["app.matcha.routes.intake.symlink_public"]
    assert mod.LINK_BUDGETS == {"turn": (40, 240), "upload": (24, 200), "submit": (6, 120)}

    for kind, (per_link, per_company) in mod.LINK_BUDGETS.items():
        effective = _effective_hourly(mod, kind)
        assert effective > per_link, (
            f"per-IP hourly rate for {kind} ({effective}) must stay above the per-link "
            f"budget ({per_link}) or per-IP becomes the binding constraint"
        )
        assert effective < per_company, (
            f"per-IP hourly rate for {kind} ({effective}) must stay below the per-company "
            f"budget ({per_company}) or one address can exhaust the whole tenant's hour"
        )


def test_unlock_is_bounded_per_link_and_has_no_company_budget(public_router):
    """The passcode is company-wide, so a per-company unlock budget would let
    one attacker lock every legitimate recipient of a tenant out for the hour.
    Guessing is bounded per link and, across links, per IP."""
    import sys

    mod = sys.modules["app.matcha.routes.intake.symlink_public"]
    assert "unlock" not in mod.LINK_BUDGETS
    assert mod.UNLOCK_PER_LINK_HOURLY == 12
    assert _effective_hourly(mod, "unlock") > mod.UNLOCK_PER_LINK_HOURLY


def test_every_public_endpoint_charges_a_per_ip_limit(public_router):
    """The per-IP table is only a backstop if every public handler is behind it.
    `DELETE /sym/{token}/attachments/{id}` was the one that wasn't: it ran a
    token lookup (a DB round-trip) per request with nothing charged."""
    import inspect

    for route in public_router.routes:
        src = inspect.getsource(route.endpoint)
        assert "_ip_limit(" in src, f"{sorted(route.methods)} {route.path} charges no per-IP limit"


def test_rate_limit_numbers_live_in_the_tables(public_router):
    """No inline magic numbers: `check_rate_limit` is reached through `_ip_limit`
    or `_budget` (which read IP_LIMITS / LINK_BUDGETS), and the one direct call
    passes a named constant, not a literal."""
    import ast
    import inspect
    import sys

    mod = sys.modules["app.matcha.routes.intake.symlink_public"]
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
        assert not isinstance(limit_arg, ast.Constant), (
            "the unlock per-link budget must be UNLOCK_PER_LINK_HOURLY, not a literal"
        )


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
        for route in admin_router.routes
        if not _guarded(route.dependant)
    ]
    assert ungated == [], f"endpoints not behind require_symlink_admin: {ungated}"
    # And the gate is the narrowed one, not the shared dep that also admits `individual`.
    assert "Depends(require_admin_or_client)" not in inspect.getsource(mod)
