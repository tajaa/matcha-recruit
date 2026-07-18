"""Carrier capability tiering — DB-free.

The Claims Bridge + Risk-to-Rate features must stay inert until a partner sandbox
confirms the data exists. In mock mode everything is exposed (so the whole product
is demoable); in live mode only the confirmed set is on.
"""

from app.matcha.services import coterie_service as cs


def test_parse_caps_all_and_list_and_default():
    assert cs._parse_caps("all", cs._CONFIRMED_CAPABILITIES) == cs._ALL_CAPABILITIES
    assert cs._parse_caps("quote, bind", cs._CONFIRMED_CAPABILITIES) == {"quote", "bind"}
    # empty falls back to the given default
    assert cs._parse_caps("", cs._CONFIRMED_CAPABILITIES) == set(cs._CONFIRMED_CAPABILITIES)
    # unknown tokens are dropped (only known capabilities survive)
    assert cs._parse_caps("quote,bogus", cs._CONFIRMED_CAPABILITIES) == {"quote"}


def test_mock_mode_exposes_all_capabilities(monkeypatch):
    monkeypatch.setattr(cs, "COTERIE_MODE", "mock")
    monkeypatch.setattr(cs, "COTERIE_MOCK_CAPS", set(cs._ALL_CAPABILITIES))
    for cap in ("quote", "bind", "loss_runs", "fnol", "credits"):
        assert cs.has_capability(cap) is True


def test_live_mode_confirmed_only(monkeypatch):
    monkeypatch.setattr(cs, "COTERIE_MODE", "live")
    monkeypatch.setattr(cs, "COTERIE_CAPS", set(cs._CONFIRMED_CAPABILITIES))
    assert cs.has_capability("quote") is True
    assert cs.has_capability("bind") is True
    # unconfirmed carrier data features are off in live mode until sandbox proves them
    assert cs.has_capability("loss_runs") is False
    assert cs.has_capability("fnol") is False
    assert cs.has_capability("credits") is False
