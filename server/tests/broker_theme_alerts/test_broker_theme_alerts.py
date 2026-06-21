"""Pure tests for broker theme-alert helpers (DB/Gemini paths smoke-tested vs dev)."""

from app.matcha.services import broker_theme_alerts as bta


def test_slug_within_metric_key_limit():
    s = bta._slug("Catastrophic forklift maintenance failures throughout the whole site", "Sherman Oaks Distribution Center")
    assert s.startswith("theme:")
    assert len(s) <= 40  # broker_risk_alerts.metric_key is varchar(40)


def test_slug_stable_and_distinct():
    assert bta._slug("Forklift failures", "Sherman Oaks") == bta._slug("Forklift failures", "Sherman Oaks")
    assert bta._slug("Forklift failures", "Sherman Oaks") != bta._slug("Storage hotspot", "Hollywood")


def test_evaluate_filters_and_maps_severity():
    themes = [
        {"label": "Forklift failures", "severity": "critical", "location_name": "Sherman Oaks", "incident_count": 4, "insight": "i", "recommendation": "r"},
        {"label": "Storage hotspot", "severity": "high", "location_name": "Hollywood", "incident_count": 3},
        {"label": "Minor stuff", "severity": "medium", "location_name": "X", "incident_count": 2},
        {"label": "Tiny", "severity": "low", "incident_count": 1},
    ]
    out = bta.evaluate_theme_alerts(themes)
    assert len(out) == 2  # medium + low dropped
    assert out[0]["severity"] == "critical"  # critical sorts first
    sev = {o["theme_label"]: o["severity"] for o in out}
    assert sev["Forklift failures"] == "critical"
    assert sev["Storage hotspot"] == "warning"  # high → warning


def test_headline_no_double_location():
    out = bta.evaluate_theme_alerts([
        {"label": "Insubordination at Exit Corp", "severity": "high", "location_name": "Exit Corp", "incident_count": 3}])
    assert out[0]["message"].count("Exit Corp") == 1


def test_headline_appends_location_when_absent():
    out = bta.evaluate_theme_alerts([
        {"label": "Forklift failures", "severity": "critical", "location_name": "Sherman Oaks", "incident_count": 2}])
    assert "at Sherman Oaks" in out[0]["message"]


def test_cap_per_client():
    themes = [{"label": f"Theme {i}", "severity": "critical", "incident_count": i} for i in range(10)]
    assert len(bta.evaluate_theme_alerts(themes)) == bta.MAX_THEME_ALERTS_PER_CLIENT
