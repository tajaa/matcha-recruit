"""Pure-logic tests for broker positive-milestone detection + outreach anonymization.

No DB / no worker — only the pure functions:
- app.workers.tasks.broker_milestones (evaluate_milestones, decide_milestone_action)
- app.matcha.services.broker_outreach (_anonymize_context, _normalize_prompts)
"""

import json

from app.workers.tasks.broker_milestones import (
    evaluate_milestones,
    decide_milestone_action,
    INCIDENT_FREE_TIERS,
)
from app.matcha.services.broker_outreach import (
    _anonymize_context,
    _normalize_prompts,
    PII_DENYLIST,
    ALLOWED_RESOURCES,
)


# ── metrics fixture builder ──────────────────────────────────────────────────
def _metrics(**over):
    """A baseline metrics dict (no milestones firing); override per test."""
    m = {
        "industry": "Manufacturing",
        "headcount": 100,
        "recordable_cases": 3,
        "dart_cases": 1,
        "lost_days": 10,
        "trir": 5.0,
        "dart_rate": 2.0,
        "days_since_last_recordable": 30,
        "ever_recordable": True,
        "benchmark": {"sector": "31", "label": "Manufacturing", "trir": 4.0, "dart": 2.0},
        "premium_impact": {"direction": "neutral", "annual_impact_dollars": 0},
        "quarterly": [{"quarter": "2026-Q1", "recordable": 1, "dart": 0, "non_dart": 1, "lost_days": 0}],
        "prior": {
            "recordable_cases": 3, "dart_cases": 1, "lost_days": 10,
            "trir": 5.0, "dart_rate": 2.0,
            "trir_delta_pct": 0.0, "dart_delta_pct": 0.0, "lost_days_delta_pct": 0.0,
        },
        "data_quality": {"insufficient_population": False, "headcount_missing": False},
    }
    m.update(over)
    return m


def _keys(cands):
    return {c["milestone_key"] for c in cands}


# ── incident-free streak tiers ───────────────────────────────────────────────
def test_incident_free_fires_highest_tier_only():
    assert _keys(evaluate_milestones(_metrics(days_since_last_recordable=100))) == {"incident_free_90"}
    assert _keys(evaluate_milestones(_metrics(days_since_last_recordable=200))) == {"incident_free_180"}
    assert _keys(evaluate_milestones(_metrics(days_since_last_recordable=400))) == {"incident_free_365"}


def test_incident_free_below_first_tier_does_not_fire():
    assert "incident_free_90" not in _keys(evaluate_milestones(_metrics(days_since_last_recordable=45)))


def test_incident_free_requires_ever_recordable():
    # A never-recordable company has days_since=None → not a 365-day milestone.
    cands = evaluate_milestones(_metrics(ever_recordable=False, days_since_last_recordable=None))
    assert not any(c["milestone_family"] == "incident_free" for c in cands)


def test_incident_free_tiers_constant_ordered():
    assert INCIDENT_FREE_TIERS == (90, 180, 365)


# ── DART-free year ───────────────────────────────────────────────────────────
def test_dart_free_year_fires_on_improvement():
    cands = evaluate_milestones(_metrics(dart_cases=0, prior={**_metrics()["prior"], "dart_cases": 3}))
    assert "dart_free_year" in _keys(cands)


def test_dart_free_year_needs_prior_dart():
    # Zero DART this year AND zero last year = no genuine improvement → no fire.
    cands = evaluate_milestones(_metrics(dart_cases=0, prior={**_metrics()["prior"], "dart_cases": 0}))
    assert "dart_free_year" not in _keys(cands)


# ── TRIR below benchmark (rate-based → suppressed on thin data) ───────────────
def test_trir_below_benchmark_fires_when_improving():
    m = _metrics(trir=2.0, prior={**_metrics()["prior"], "trir_delta_pct": -12.0})
    assert "trir_below_benchmark" in _keys(evaluate_milestones(m))


def test_trir_below_benchmark_needs_improvement_trend():
    # Below benchmark but trending UP → not a milestone.
    m = _metrics(trir=2.0, prior={**_metrics()["prior"], "trir_delta_pct": 5.0})
    assert "trir_below_benchmark" not in _keys(evaluate_milestones(m))


def test_trir_below_benchmark_suppressed_on_thin_population():
    m = _metrics(
        trir=2.0,
        prior={**_metrics()["prior"], "trir_delta_pct": -12.0},
        data_quality={"insufficient_population": True, "headcount_missing": False},
    )
    assert "trir_below_benchmark" not in _keys(evaluate_milestones(m))


# ── dedup decision ───────────────────────────────────────────────────────────
def test_decide_action_insert_rearm_skip():
    cand = {"milestone_key": "incident_free_90"}
    assert decide_milestone_action(None, cand) == "insert"
    assert decide_milestone_action({"superseded_at": "2026-01-01"}, cand) == "rearm"
    assert decide_milestone_action({"superseded_at": None}, cand) == "skip"


# ── outreach anonymization (the "AI-shielded" guarantee) ──────────────────────
def _collect_keys(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            _collect_keys(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_keys(v, acc)


def test_anonymize_context_has_no_pii_keys():
    ctx = _anonymize_context(
        wc_metrics=_metrics(),
        behavioral={"current_count": 4, "prior_count": 1, "delta_pct": 300.0, "window_days": 90,
                    "attendance_count": 2, "insubordination_count": 2,
                    "hot_location": {"name": "Jane Doe Plant", "count": 3}},
        renewal_risk={"risk_band": "elevated", "turnover_pct": 18.0, "turnover_delta_pct": 5.0,
                      "lost_workdays": 12, "near_misses": 3, "behavioral_incidents": 4,
                      "triggers": ["18% turnover in last 60d"]},
        milestones=[{"milestone_family": "incident_free", "tier": 90, "title": "90 days incident-free"}],
    )
    keys = set()
    _collect_keys(ctx, keys)
    leaked = keys & set(PII_DENYLIST)
    assert not leaked, f"PII keys leaked into outreach context: {leaked}"


def test_anonymize_context_drops_location_name():
    # The free-text hot-location name must never reach the model; only a boolean.
    ctx = _anonymize_context(
        wc_metrics=_metrics(),
        behavioral={"current_count": 4, "prior_count": 1, "delta_pct": 300.0, "window_days": 90,
                    "hot_location": {"name": "Jane Doe Plant", "count": 3}},
        renewal_risk=None, milestones=None,
    )
    blob = json.dumps(ctx)
    assert "Jane Doe Plant" not in blob
    assert ctx["behavioral"]["has_location_concentration"] is True


def test_anonymize_context_keeps_aggregate_trends():
    ctx = _anonymize_context(wc_metrics=_metrics(trir=3.3), behavioral=None, renewal_risk=None, milestones=None)
    assert ctx["trir"] == 3.3
    assert ctx["benchmark_trir"] == 4.0
    assert isinstance(ctx["quarterly"], list)


# ── prompt normalization (allow-list + clamp) ─────────────────────────────────
def test_normalize_prompts_filters_and_clamps():
    raw = [
        {"title": "Good", "suggested_action": "Do X", "rationale": "because", "resource_link": "safety-guide", "tone": "celebratory"},
        {"title": "Bad URL", "suggested_action": "Do Y", "resource_link": "http://evil.example", "tone": "advisory"},
        {"title": "", "suggested_action": "no title"},            # dropped (no title)
        {"title": "No action"},                                    # dropped (no action)
        {"title": "Weird tone", "suggested_action": "Z", "tone": "screaming"},
    ]
    out = _normalize_prompts(raw)
    assert len(out) == 3
    assert out[0]["resource_link"] == "safety-guide"
    assert out[1]["resource_link"] is None          # non-allow-listed URL stripped
    assert out[2]["tone"] == "advisory"             # invalid tone coerced
    assert all(p["resource_link"] in (None, *ALLOWED_RESOURCES) for p in out)
