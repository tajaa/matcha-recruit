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


def test_per_ip_limits_are_a_flood_backstop_not_the_binding_constraint(public_router):
    """Per-link/per-company budgets are the cost governors; per-IP is a flood
    backstop. A bulk send puts a whole office behind one NAT address, so if a
    per-IP ceiling ever drops below the matching per-link budget it starts 429ing
    legitimate recipients instead of bounding cost. See services/symlink/CLAUDE.md.
    """
    import inspect
    import re
    import sys

    mod = sys.modules["app.matcha.routes.intake.symlink_public"]
    src = inspect.getsource(mod)

    # `_budget(token, company_id, "<kind>", <per_link>, <per_company>)`
    per_link = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r'_budget\(\s*token,\s*company_id,\s*"(\w+)",\s*(\d+),\s*(\d+)\)', src)
    }
    assert per_link == {"turn": 40, "upload": 24, "submit": 6}

    hourly = {key: limit for key, (limit, window) in mod.IP_LIMITS.items() if window == 3600}
    for kind, link_budget in per_link.items():
        matching = [v for k, v in hourly.items() if k.startswith(f"symlink_{kind}_ip")]
        assert matching, f"no hourly per-IP limit for {kind}"
        assert min(matching) > link_budget, (
            f"per-IP hourly limit for {kind} ({min(matching)}) must stay above the "
            f"per-link budget ({link_budget}) or it becomes the binding constraint"
        )

    # Unlock brute force is bounded per link, not per IP.
    assert 'check_rate_limit(token, "symlink_unlock_link", 12, 3600)' in src
    assert mod.IP_LIMITS["symlink_unlock_ip"][0] > 12


def test_every_ip_limit_call_goes_through_the_table(public_router):
    """No inline per-IP magic numbers — the table is the one place to tune them."""
    import inspect
    import re
    import sys

    src = inspect.getsource(sys.modules["app.matcha.routes.intake.symlink_public"])
    inline = re.findall(r'check_rate_limit\(\s*(?:ip|client_ip\(request\))\s*,', src)
    assert inline == [], "per-IP limits must call _ip_limit(), not check_rate_limit() directly"


def test_admin_router_is_company_admin_only(admin_router):
    """Sym-link is company-scoped: it needs a tenant, a roster and a company
    passcode. `individual` (personal matcha-work, no company) must not reach it,
    and neither must `employee` — the recipient side is the unauthenticated
    /sym/{token} surface, not this router."""
    import inspect
    import sys

    mod = sys.modules["app.matcha.routes.symlink"]
    src = inspect.getsource(mod)

    assert 'require_roles("admin", "client")' in src
    # Match the call, not the name — the module comment explains why the shared
    # dep was dropped and legitimately mentions it.
    assert "Depends(require_admin_or_client)" not in src, "shared dep also admits `individual`"
    # Every authenticated endpoint goes through the narrowed gate.
    assert src.count("Depends(require_symlink_admin)") >= 15
