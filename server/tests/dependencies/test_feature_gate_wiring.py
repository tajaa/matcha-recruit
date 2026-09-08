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
# Anchored on THIS file, not the CWD. A relative Path() here resolves against
# wherever pytest was invoked, so `pytest server/tests` from the repo root found
# no files at all, USAGES came back empty, and every parametrized case below
# silently vanished — the same defect this suite's own repairs hit twice
# (tests/infrastructure/test_ai_chat.py, tests/compliance/
# test_compliance_schema_redesign.py).
_SERVER = Path(__file__).resolve().parents[2]
ROUTE_ROOTS = [
    _SERVER / "app" / "matcha" / "routes",
    _SERVER / "app" / "core" / "routes",
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


def _case(path: str, lineno: int, flag: str):
    """One parametrized case, xfailed STRICTLY if the flag is a known defect.

    `pytest.xfail()` inside the body would be wrong here: the imperative form
    is never strict and can never XPASS, so adding `offer_letters_plus` to
    ALL_FEATURES would leave this reporting XFAIL forever and KNOWN_UNGRANTABLE
    would rot as dead scaffolding. server/CLAUDE.md commits this suite to
    `xfail(strict=True)` precisely so a fix forces the marker off.
    """
    marks = []
    if flag in KNOWN_UNGRANTABLE:
        marks.append(pytest.mark.xfail(
            strict=True,
            reason=f"{flag} is gated but grantable nowhere — see KNOWN_UNGRANTABLE",
        ))
    return pytest.param(path, lineno, flag, marks=marks)


@pytest.mark.parametrize(
    "path,lineno,flag",
    [_case(*usage) for usage in USAGES],
    ids=[f"{Path(p).name}:{line}:{flag}" for p, line, flag in USAGES],
)
def test_every_gated_flag_is_a_real_feature(path, lineno, flag):
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


def _normalize(flag: str) -> str:
    return flag.replace("_", "").lower()


def test_a_gated_flag_is_never_a_punctuation_variant_of_a_real_one():
    """`ircopilot` gated where `ir_copilot` exists is a typo the 403 hides.

    This deliberately compares against ALL_FEATURES, not against the gated set.
    An earlier version compared gated flags to each other after stripping
    underscores, which can only fire when two gates differ *purely* in
    underscore placement — a shape this codebase does not contain, so it passed
    unconditionally. It also could not detect the `hris_import` vs `hris` case
    its own docstring claimed, since those normalize to different strings.
    Prefix matching is not the answer either: `inventory`/`inventory_voice` and
    `osha_logs`/`osha_export` are all real, deliberately separate flags.
    """
    real_by_normal = {}
    for feature in ALL_FEATURES:
        real_by_normal.setdefault(_normalize(feature), set()).add(feature)

    typos = []
    for flag in sorted({flag for _, _, flag in USAGES}):
        if flag in ALL_FEATURES:
            continue
        near = sorted(real_by_normal.get(_normalize(flag), set()))
        if near:
            typos.append((flag, near))
    assert not typos, (
        f"gated flags that are a punctuation/case variant of a real feature "
        f"(so the gate 403s forever while the flag it meant exists): {typos}"
    )


def test_no_two_gates_spell_the_same_flag_differently():
    """Two mounts normalizing to one flag means one of them is dead."""
    gated = sorted({flag for _, _, flag in USAGES})
    by_normal: dict[str, list[str]] = {}
    for flag in gated:
        by_normal.setdefault(_normalize(flag), []).append(flag)
    collisions = {norm: names for norm, names in by_normal.items() if len(names) > 1}
    assert not collisions, f"flags gated under more than one spelling: {collisions}"
