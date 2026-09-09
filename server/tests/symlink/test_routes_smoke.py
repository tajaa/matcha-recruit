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
