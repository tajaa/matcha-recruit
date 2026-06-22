"""Pure tests for grounded exclusion-gap matcher (DB gather smoke-tested vs dev)."""

from app.matcha.services import exclusion_gap as eg

NO_SIGNALS = {
    "biometric_present": False, "biometric_consented": False, "abuse_program": False,
    "infection_program": False, "ai_audit": False, "has_drivers": False, "wildfire_state": False,
}


def _by_key(result):
    return {e["key"]: e for e in result["exclusions"]}


def test_industry_keyword_drives_relevance():
    r = eg.analyze("Senior living / assisted nursing", NO_SIGNALS)
    keys = _by_key(r)
    assert "abuse_molestation" in keys and keys["abuse_molestation"]["status"] == "exposed"
    assert "communicable_disease" in keys


def test_silent_cyber_is_inherent_monitor():
    r = eg.analyze("anything at all", NO_SIGNALS)
    assert _by_key(r)["silent_cyber"]["status"] == "monitor"


def test_signal_drives_relevance_and_mitigation():
    # biometric present but not consented → exposed
    r1 = _by_key(eg.analyze("office services", {**NO_SIGNALS, "biometric_present": True}))
    assert r1["biometric_bipa"]["status"] == "exposed"
    # consented → mitigated
    r2 = _by_key(eg.analyze("office services", {**NO_SIGNALS, "biometric_present": True, "biometric_consented": True}))
    assert r2["biometric_bipa"]["status"] == "mitigated"


def test_abuse_program_mitigates():
    r = _by_key(eg.analyze("childcare", {**NO_SIGNALS, "abuse_program": True}))
    assert r["abuse_molestation"]["status"] == "mitigated"


def test_wildfire_state_trigger():
    assert "wildfire" not in _by_key(eg.analyze("retail", NO_SIGNALS))
    assert "wildfire" in _by_key(eg.analyze("retail", {**NO_SIGNALS, "wildfire_state": True}))


def test_irrelevant_omitted_and_exposed_sorts_first():
    r = eg.analyze("manufacturing chemical plant", NO_SIGNALS)
    keys = _by_key(r)
    assert "pfas" in keys and keys["pfas"]["status"] == "exposed"
    assert "abuse_molestation" not in keys  # no keyword/signal match
    statuses = [e["status"] for e in r["exclusions"]]
    assert statuses == sorted(statuses, key=lambda s: {"exposed": 0, "monitor": 1, "mitigated": 2}[s])


def test_external_only_industry_and_state():
    r = eg.external_exclusions("hospitality hotel", "CA")
    keys = _by_key(r)
    assert "assault_battery" in keys
    assert "wildfire" in keys  # CA
    # "hospitality" is a biometric_bipa keyword; external path has no DB signal, so
    # it can only ever be keyword-exposed (never mitigated).
    assert keys["biometric_bipa"]["status"] == "exposed"
