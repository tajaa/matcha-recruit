"""Pure tests for the experience-mod proxy.

No DB / app boot."""

from app.matcha.services.insurance import wc_depth


# --- proxy_mod (directional actual ÷ expected) -----------------------------

def test_proxy_mod_basic():
    assert wc_depth.proxy_mod(120_000, 100_000) == 1.2   # adverse
    assert wc_depth.proxy_mod(50_000, 100_000) == 0.5    # favorable
    assert wc_depth.proxy_mod(100_000, 100_000) == 1.0   # on plan


def test_proxy_mod_no_expected_base_is_none():
    assert wc_depth.proxy_mod(50_000, 0) is None
    assert wc_depth.proxy_mod(50_000, None) is None      # type: ignore[arg-type]
    assert wc_depth.proxy_mod(0, -10) is None
