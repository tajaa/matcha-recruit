"""Auto tier routing.

`auto` is the client's default, so this decides which model every Merlin turn
runs on. Two properties matter more than accuracy:

  - a free plan never pays for a classification it would have discarded, and
  - a classifier failure routes UP. Falling back to `lite` would hand the cheap
    single-shot answer to exactly the vague design request that `auto` exists to
    escalate — and it would look like the feature working, not failing.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_router.py -q
"""
import os

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services import merlin_router  # noqa: E402
from app.cappe.services.merlin_router import route_tier  # noqa: E402

_PRO = "pro"
_FREE = "free"


@pytest.fixture
def no_classifier(monkeypatch):
    """Assert the classifier is NOT called on this path."""
    calls = []

    async def _boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("classifier should not have been called")

    monkeypatch.setattr(merlin_router, "_classify", _boom)
    return calls


@pytest.fixture
def classifier(monkeypatch):
    """Script what `_classify` returns — a TIER (it maps the model's verdict
    itself), or None for a failure."""

    def _install(tier):
        async def _fake(*_a, **_k):
            return tier

        monkeypatch.setattr(merlin_router, "_classify", _fake)

    return _install


# --- pinned tiers ------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_pinned_tier_is_clamped_not_routed(no_classifier):
    tier, routed = await route_tier("max", _PRO, message="anything")
    assert (tier, routed) == ("max", False)


@pytest.mark.asyncio
async def test_a_pinned_premium_tier_still_clamps_for_free_plans(no_classifier):
    tier, routed = await route_tier("max", _FREE, message="anything")
    assert (tier, routed) == ("lite", False)


# --- free plans --------------------------------------------------------------

@pytest.mark.asyncio
async def test_free_plans_never_reach_the_classifier(no_classifier):
    """`auto` clamps to lite on the plan gate, so a free turn adds no call whose
    answer it could act on."""
    tier, routed = await route_tier(
        "auto", _FREE, message="completely redesign this page to look premium"
    )
    assert tier == "lite"
    assert routed is False
    assert not no_classifier


# --- heuristics (free verdicts) ----------------------------------------------

@pytest.mark.asyncio
async def test_design_language_routes_to_max_without_a_call(no_classifier):
    """The requests that produced the bad-restyle incidents are exactly the ones
    that need the screenshot loop — no need to ask a model about them."""
    for message in (
        "make this look professional",
        "redesign the hero",
        "the whole page feels dated, make it modern",
    ):
        tier, routed = await route_tier("auto", _PRO, message=message)
        assert (tier, routed) == ("max", True), message


@pytest.mark.asyncio
async def test_a_short_edit_on_a_selected_section_routes_to_lite(no_classifier):
    tier, routed = await route_tier(
        "auto", _PRO, message="change this to Book Now", has_selected_block=True
    )
    assert (tier, routed) == ("lite", True)


@pytest.mark.asyncio
async def test_a_short_message_without_a_selection_is_not_assumed_trivial(classifier):
    """Without a selected section even a short message may mean a page-wide
    change, so it goes to the classifier rather than defaulting to lite."""
    classifier("standard")
    tier, _ = await route_tier("auto", _PRO, message="warmer colors please")
    assert tier == "regular"


# --- classifier --------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("expected", ["lite", "regular", "max"])
async def test_a_classified_tier_is_used_as_is(classifier, expected):
    classifier(expected)
    tier, routed = await route_tier("auto", _PRO, message="add a section about our team")
    assert (tier, routed) == (expected, True)


def test_complexity_verdicts_map_onto_real_tiers():
    """The model answers in complexity words; those must land on tiers that
    exist, or every classified turn silently falls back."""
    from app.cappe.services.merlin_catalog import MODEL_TIERS

    assert set(merlin_router._COMPLEXITY_TIERS) == {"trivial", "standard", "complex"}
    for tier in merlin_router._COMPLEXITY_TIERS.values():
        assert tier in MODEL_TIERS


@pytest.mark.asyncio
async def test_a_classifier_failure_routes_up_not_down(classifier):
    """The load-bearing fallback: an underworked answer to a design request is
    indistinguishable from Merlin being bad at design."""
    classifier(None)
    tier, routed = await route_tier("auto", _PRO, message="add a section about our team")
    assert tier == "regular"
    assert routed is True


@pytest.mark.asyncio
async def test_an_unknown_verdict_falls_back_rather_than_crashing(classifier):
    classifier("catastrophic")
    tier, _ = await route_tier("auto", _PRO, message="add a section about our team")
    assert tier == "regular"


@pytest.mark.asyncio
async def test_an_empty_message_does_not_reach_the_classifier(no_classifier):
    tier, _ = await route_tier("auto", _PRO, message="   ")
    assert tier == "lite"
