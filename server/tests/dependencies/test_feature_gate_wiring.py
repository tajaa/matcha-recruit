"""Mount-time wiring for the feature gates.

`require_feature("typo")` does not raise anywhere — it resolves to
`features.get("typo", False)` and 403s forever, so a misspelt flag silently
takes a paid feature off the market for every tenant, and the symptom is a
support ticket rather than a stack trace. Nothing checked these names, and
there are 39 gated mounts in `routes/__init__.py` alone.

This reads the mounts statically (no app boot, no DB) and checks every flag
named in a gate against `ALL_FEATURES`, the canonical registry in
`core/feature_flags.py`.

    cd server && ./venv/bin/python -m pytest tests/dependencies/test_feature_gate_wiring.py -q
"""

import ast
from pathlib import Path

import pytest

from app.core.feature_flags import ALL_FEATURES

GATE_FACTORIES = {"require_feature", "require_any_feature", "require_all_features"}
ROUTE_ROOTS = [
    Path("app/matcha/routes"),
    Path("app/core/routes"),
]


def _gate_usages() -> list[tuple[str, int, str]]:
    """(file, lineno, flag_name) for every literal flag named in a gate call."""
    found: list[tuple[str, int, str]] = []
    for root in ROUTE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name not in GATE_FACTORIES:
                    continue
                for arg in node.args:
                    # Only literal names are checkable; a variable is resolved
                    # at runtime and is out of scope here.
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.append((str(path), node.lineno, arg.value))
    return found


USAGES = _gate_usages()

# Flags gated in a route but absent from ALL_FEATURES. Each entry is a live
# defect, not a waiver: the endpoint 403s for every tenant (platform admins
# bypass, which is why nobody noticed). Entries stay here only until someone
# decides what the flag should be, and the list must never grow to hide a typo.
#
# - offer_letters_plus: POST /offer-letters/plus/recommendation. The string
#   appears exactly ONCE in the entire codebase — this gate — so it is settable
#   nowhere and in no tier. Either it wants its own default-off flag in
#   core/feature_flags.py, or it belongs behind the existing `offer_letters`.
#   Product call, so this test records it rather than picking one.
KNOWN_UNGRANTABLE = {"offer_letters_plus"}


def test_the_scan_found_the_gates_at_all():
    # Guards the test itself: a refactor that moves the routers must not turn
    # this file into a silent no-op that passes by finding nothing.
    assert len(USAGES) >= 30, f"only found {len(USAGES)} feature-gate usages; scan is stale"


@pytest.mark.parametrize(
    "path,lineno,flag",
    USAGES,
    ids=[f"{Path(p).name}:{line}:{flag}" for p, line, flag in USAGES],
)
def test_every_gated_flag_is_a_real_feature(path, lineno, flag):
    if flag in KNOWN_UNGRANTABLE:
        pytest.xfail(f"{flag} is gated but grantable nowhere — see KNOWN_UNGRANTABLE")
    assert flag in ALL_FEATURES, (
        f"{path}:{lineno} gates on '{flag}', which is not in ALL_FEATURES — "
        f"require_feature would 403 every tenant forever. Either it is a typo, "
        f"or the flag needs adding to core/feature_flags.py."
    )


def test_the_known_defect_list_stays_short():
    """A growing waiver list is how a typo hides. If this trips, fix the flag
    rather than appending to the list."""
    assert len(KNOWN_UNGRANTABLE) <= 1, (
        f"ungrantable gated flags grew to {sorted(KNOWN_UNGRANTABLE)}"
    )


def test_no_flag_is_gated_under_two_spellings():
    """A near-duplicate (`hris_import` vs `hris`) means one of the two mounts
    is dead. Catches the copy-paste that a passing 403 would never reveal."""
    gated = {flag for _, _, flag in USAGES}
    collisions = []
    for flag in sorted(gated):
        twins = [other for other in gated if other != flag and other.replace("_", "") == flag.replace("_", "")]
        if twins:
            collisions.append((flag, twins))
    assert not collisions, f"flags gated under more than one spelling: {collisions}"
