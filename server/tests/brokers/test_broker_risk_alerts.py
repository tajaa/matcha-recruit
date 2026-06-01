"""Pure-logic tests for the broker risk-alert trend rules + cooldown decision.

No DB / no worker — only the pure functions in
app.workers.tasks.broker_risk_alerts (evaluate_trends, decide_action,
should_suppress).
"""

from datetime import datetime, timedelta

from app.workers.tasks.broker_risk_alerts import (
    evaluate_trends,
    decide_action,
    should_suppress,
    THRESHOLDS,
    COOLDOWN_DAYS,
    _EPOCH,
)


# ── metrics fixture builder ──────────────────────────────────────────────────
def _metrics(**over):
    """A healthy baseline metrics dict; override individual fields per test."""
    m = {
        "headcount": 100,
        "recordable_cases": 5,
        "dart_cases": 2,
        "lost_days": 20,
        "trir": 5.0,
        "dart_rate": 2.0,
        "days_since_last_recordable": 30,
        "premium_impact": {"direction": "neutral", "annual_impact_dollars": 0},
        "prior": {
            "recordable_cases": 5,
            "trir": 5.0,
            "dart_rate": 2.0,
            "lost_days": 20,
            "trir_delta_pct": 0.0,
            "dart_delta_pct": 0.0,
            "lost_days_delta_pct": 0.0,
            "recordable_delta_pct": 0.0,
        },
        "data_quality": {"insufficient_population": False, "headcount_missing": False},
    }
    m.update(over)
    return m


def _keys(candidates):
    return {c["metric_key"] for c in candidates}


# ── suppression: rate metrics only ───────────────────────────────────────────
def test_suppress_flags_rates_unreliable():
    assert should_suppress(_metrics(data_quality={"insufficient_population": True, "headcount_missing": False})) is True
    assert should_suppress(_metrics(headcount=None, data_quality={"insufficient_population": False, "headcount_missing": True})) is True


def test_thin_population_suppresses_rate_metrics_but_not_counts():
    # Thin population: a big TRIR/DART spike must NOT fire (rates unreliable)...
    m = _metrics(
        data_quality={"insufficient_population": True, "headcount_missing": False},
        trir=8.0, dart_rate=4.0,
        lost_days=40, recordable_cases=3,
        premium_impact={"direction": "increase", "annual_impact_dollars": 9000},
        prior={
            **_metrics()["prior"],
            "trir": 5.0, "trir_delta_pct": 60.0,
            "dart_rate": 2.0, "dart_delta_pct": 100.0,
            "lost_days": 10, "lost_days_delta_pct": 300.0,
            "recordable_cases": 0,
        },
    )
    keys = _keys(evaluate_trends(m, prior_premium_direction="neutral"))
    assert "trir" not in keys
    assert "dart" not in keys
    assert "premium_increase" not in keys
    # ...but count-based rules still fire — they need no hours estimate.
    assert "lost_days" in keys
    assert "claim_free_broken" in keys


def test_healthy_company_no_alerts():
    assert evaluate_trends(_metrics()) == []


# ── TRIR rule + boundaries ───────────────────────────────────────────────────
def test_trir_just_above_threshold_fires():
    # +16% delta, absolute rise 0.8 (>= 0.5 guard)
    m = _metrics(trir=5.8, prior={**_metrics()["prior"], "trir": 5.0, "trir_delta_pct": 16.0})
    assert "trir" in _keys(evaluate_trends(m))


def test_trir_just_below_threshold_suppressed():
    m = _metrics(trir=5.7, prior={**_metrics()["prior"], "trir": 5.0, "trir_delta_pct": 14.0})
    assert "trir" not in _keys(evaluate_trends(m))


def test_trir_big_pct_but_tiny_absolute_rise_suppressed():
    # 100% delta but only +0.2 absolute — small-base guard blocks it.
    m = _metrics(trir=0.4, prior={**_metrics()["prior"], "trir": 0.2, "trir_delta_pct": 100.0})
    assert "trir" not in _keys(evaluate_trends(m))


def test_trir_severity_escalates_to_critical():
    # delta >= threshold * CRITICAL_MULTIPLIER (15 * 2 = 30)
    m = _metrics(trir=7.0, prior={**_metrics()["prior"], "trir": 5.0, "trir_delta_pct": 40.0})
    cand = next(c for c in evaluate_trends(m) if c["metric_key"] == "trir")
    assert cand["severity"] == "critical"


# ── DART + lost days ─────────────────────────────────────────────────────────
def test_dart_fires_above_threshold():
    m = _metrics(dart_rate=2.6, prior={**_metrics()["prior"], "dart_rate": 2.0, "dart_delta_pct": 30.0})
    assert "dart" in _keys(evaluate_trends(m))


def test_lost_days_requires_absolute_rise():
    # 30% delta but only +3 days absolute (< 5 guard)
    m = _metrics(lost_days=13, prior={**_metrics()["prior"], "lost_days": 10, "lost_days_delta_pct": 30.0})
    assert "lost_days" not in _keys(evaluate_trends(m))

    m2 = _metrics(lost_days=20, prior={**_metrics()["prior"], "lost_days": 10, "lost_days_delta_pct": 100.0})
    assert "lost_days" in _keys(evaluate_trends(m2))


# ── claim-free streak broken ─────────────────────────────────────────────────
def test_claim_free_broken_fires_only_on_clean_prior():
    m = _metrics(recordable_cases=2, prior={**_metrics()["prior"], "recordable_cases": 0})
    assert "claim_free_broken" in _keys(evaluate_trends(m))


def test_claim_free_not_broken_when_prior_had_recordables():
    m = _metrics(recordable_cases=2, prior={**_metrics()["prior"], "recordable_cases": 3})
    assert "claim_free_broken" not in _keys(evaluate_trends(m))


# ── premium flip vs benchmark-relative direction ─────────────────────────────
def test_premium_flip_to_increase_fires():
    m = _metrics(premium_impact={"direction": "increase", "annual_impact_dollars": 4000})
    cands = evaluate_trends(m, prior_premium_direction="neutral")
    assert "premium_increase" in _keys(cands)


def test_premium_no_alert_when_already_increasing_and_not_worse():
    m = _metrics(premium_impact={"direction": "increase", "annual_impact_dollars": 4000})
    # Last cycle already "increase" and dollars not materially higher → no re-alert.
    cands = evaluate_trends(m, prior_premium_direction="increase", prior_premium_dollars=4000)
    assert "premium_increase" not in _keys(cands)


def test_premium_realerts_when_worsens_materially():
    m = _metrics(premium_impact={"direction": "increase", "annual_impact_dollars": 6000})
    # +50% over prior 4000 (>= 20% worsen) → fires even though still "increase".
    cands = evaluate_trends(m, prior_premium_direction="increase", prior_premium_dollars=4000)
    assert "premium_increase" in _keys(cands)


def test_premium_critical_above_dollar_threshold():
    m = _metrics(premium_impact={"direction": "increase", "annual_impact_dollars": 30000})
    cand = next(c for c in evaluate_trends(m, prior_premium_direction="neutral")
                if c["metric_key"] == "premium_increase")
    assert cand["severity"] == "critical"


# ── cooldown / state machine ─────────────────────────────────────────────────
_CAND = {"metric_key": "trir", "severity": "warning"}
_NOW = datetime(2026, 5, 27, 12, 0, 0)


def test_decide_insert_when_no_existing_row():
    assert decide_action(None, _CAND, now=_NOW) == "insert"


def test_decide_skip_within_cooldown():
    existing = {"id": "x", "resolved_at": None, "severity": "warning",
                "last_alerted_at": _NOW - timedelta(days=COOLDOWN_DAYS - 1)}
    assert decide_action(existing, _CAND, now=_NOW) == "skip"


def test_decide_send_after_cooldown():
    existing = {"id": "x", "resolved_at": None, "severity": "warning",
                "last_alerted_at": _NOW - timedelta(days=COOLDOWN_DAYS + 1)}
    assert decide_action(existing, _CAND, now=_NOW) == "send"


def test_decide_send_on_resolve_rearm():
    existing = {"id": "x", "resolved_at": _NOW - timedelta(days=1), "severity": "warning",
                "last_alerted_at": _NOW}
    assert decide_action(existing, _CAND, now=_NOW) == "send"


def test_decide_send_on_escalation_within_cooldown():
    existing = {"id": "x", "resolved_at": None, "severity": "warning",
                "last_alerted_at": _NOW - timedelta(days=1)}
    crit = {"metric_key": "trir", "severity": "critical"}
    assert decide_action(existing, crit, now=_NOW) == "send"


def test_epoch_last_alerted_always_sends():
    existing = {"id": "x", "resolved_at": None, "severity": "warning", "last_alerted_at": _EPOCH}
    assert decide_action(existing, _CAND, now=_NOW) == "send"


# ── is_read suppression (broker has acknowledged the alert) ──────────────────
def test_is_read_suppresses_daily_resend():
    # Past the 1-day cooldown but broker already marked it viewed — stay silent.
    existing = {"id": "x", "resolved_at": None, "severity": "warning",
                "last_alerted_at": _NOW - timedelta(days=COOLDOWN_DAYS + 2),
                "is_read": True}
    assert decide_action(existing, _CAND, now=_NOW) == "skip"


def test_is_read_does_not_block_escalation():
    # Already read, but trend escalated warning→critical — re-notify.
    existing = {"id": "x", "resolved_at": None, "severity": "warning",
                "last_alerted_at": _NOW - timedelta(hours=1),
                "is_read": True}
    crit = {"metric_key": "trir", "severity": "critical"}
    assert decide_action(existing, crit, now=_NOW) == "send"


def test_unread_and_cooldown_elapsed_resends():
    # New default cooldown is 1 day; >1 day since last alert and unread → send.
    existing = {"id": "x", "resolved_at": None, "severity": "warning",
                "last_alerted_at": _NOW - timedelta(days=COOLDOWN_DAYS, hours=1),
                "is_read": False}
    assert decide_action(existing, _CAND, now=_NOW) == "send"


# ── behavioral friction & retention risk ─────────────────────────────────────
def _beh(current, prior, *, attendance=0, insubordination=0, location="Main Plant", window=90):
    """Build a behavioral block; delta_pct mirrors the backend (_delta_pct)."""
    delta = None if prior == 0 else round(((current - prior) / prior) * 100, 1)
    return {
        "window_days": window,
        "current_count": current,
        "prior_count": prior,
        "delta_pct": delta,
        "attendance_count": attendance,
        "insubordination_count": insubordination,
        "hot_location": {"name": location, "count": current} if current else None,
    }


def test_behavioral_absent_block_no_alert():
    # Baseline metrics carry no "behavioral" key — must not fire.
    assert "behavioral_friction" not in _keys(evaluate_trends(_metrics()))


def test_behavioral_spike_fires():
    # 5 → 11 = +120%, abs rise 6 (>= 3). Fires.
    m = _metrics(behavioral=_beh(11, 5, attendance=4, insubordination=2))
    assert "behavioral_friction" in _keys(evaluate_trends(m))


def test_behavioral_below_pct_threshold_suppressed():
    # 10 → 14 = +40% (< 50% threshold), even though abs rise 4 >= 3.
    m = _metrics(behavioral=_beh(14, 10))
    assert "behavioral_friction" not in _keys(evaluate_trends(m))


def test_behavioral_big_pct_but_tiny_absolute_suppressed():
    # 1 → 2 = +100% but abs rise only 1 (< 3). Small-base guard blocks it.
    m = _metrics(behavioral=_beh(2, 1))
    assert "behavioral_friction" not in _keys(evaluate_trends(m))


def test_behavioral_cold_start_cluster_fires():
    # No incidents prior window, fresh cluster of 4 (>= abs_min) this window.
    m = _metrics(behavioral=_beh(4, 0))
    cand = next(c for c in evaluate_trends(m) if c["metric_key"] == "behavioral_friction")
    assert cand["severity"] == "warning"  # no delta → not critical
    assert "none in the prior window" in cand["message"]


def test_behavioral_escalates_to_critical():
    # delta >= 50 * CRITICAL_MULTIPLIER (= 100). 4 → 12 = +200%.
    m = _metrics(behavioral=_beh(12, 4))
    cand = next(c for c in evaluate_trends(m) if c["metric_key"] == "behavioral_friction")
    assert cand["severity"] == "critical"


def test_behavioral_not_suppressed_by_thin_population():
    # Rate metrics suppressed for thin population, but behavioral is count-based.
    m = _metrics(
        data_quality={"insufficient_population": True, "headcount_missing": False},
        behavioral=_beh(10, 3),
    )
    assert "behavioral_friction" in _keys(evaluate_trends(m))


def test_behavioral_message_names_location_and_subtypes():
    m = _metrics(behavioral=_beh(11, 5, attendance=4, insubordination=2, location="North Clinic"))
    cand = next(c for c in evaluate_trends(m) if c["metric_key"] == "behavioral_friction")
    assert "North Clinic" in cand["message"]
    assert "4 attendance" in cand["message"]
    assert "2 insubordination" in cand["message"]
    assert "120%" in cand["message"]
