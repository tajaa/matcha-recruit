"""Discipline policy sweep — pure-function tests (no DB, no Celery execution).

The worker's DB paths are verified manually (repo convention for workers —
see test_hr_proactive_push.py). What's tested here is the feature gate and
the deterministic briefing text: the parts that are wrong silently.
"""

from app.workers.tasks.discipline_policy_sweep import (
    build_finding_briefing,
    discipline_policy_sweep_enabled,
)


def _incident(**over):
    base = {"incident_number": "IR-2026-07-0042", "title": "Needlestick in operatory 3"}
    base.update(over)
    return base


def _result(violations=None, summary="Likely sharps-handling violation."):
    return {"violations": violations if violations is not None else [], "summary": summary, "available": True}


def _violation(title="Sharps Handling", relevance="violated", confidence=0.9):
    return {"policy_title": title, "relevance": relevance, "confidence": confidence}


class TestDisciplinePolicySweepEnabled:
    def test_all_required_flags_true_enables(self):
        features = {
            "huume": True, "matcha_work": True, "discipline": True,
            "incidents": True, "handbooks": True,
        }
        assert discipline_policy_sweep_enabled(features, None) is True

    def test_missing_huume_disables(self):
        features = {"matcha_work": True, "discipline": True, "incidents": True, "handbooks": True}
        assert discipline_policy_sweep_enabled(features, None) is False

    def test_missing_handbooks_disables(self):
        # handbooks defaults True in DEFAULT_COMPANY_FEATURES, but an explicit
        # False (e.g. a tier override) must still gate the sweep off — it's
        # the corpus the policy check grounds on.
        features = {
            "huume": True, "matcha_work": True, "discipline": True,
            "incidents": True, "handbooks": False,
        }
        assert discipline_policy_sweep_enabled(features, None) is False

    def test_missing_incidents_disables(self):
        features = {"huume": True, "matcha_work": True, "discipline": True, "handbooks": True}
        assert discipline_policy_sweep_enabled(features, None) is False

    def test_resolved_via_merge_not_raw_lookup(self):
        # huume/discipline/incidents are all default-off; a company with only
        # the raw dict below (no explicit True) must resolve to disabled,
        # proving this goes through merge_company_features rather than
        # trusting caller-supplied dict keys directly.
        assert discipline_policy_sweep_enabled({}, "bespoke") is False


class TestBuildFindingBriefing:
    def test_states_incident_number_and_title(self):
        title, body = build_finding_briefing(_incident(), _result(violations=[_violation()]))
        assert "IR-2026-07-0042" in title
        assert "IR-2026-07-0042" in body
        assert "Needlestick in operatory 3" in body

    def test_singular_vs_plural_match_wording(self):
        _, one = build_finding_briefing(_incident(), _result(violations=[_violation()]))
        assert "1 possible match:" in one

        _, two = build_finding_briefing(_incident(), _result(violations=[_violation(), _violation(title="Bloodborne Pathogens")]))
        assert "2 possible matches:" in two

    def test_lists_up_to_five_violations_then_truncates(self):
        violations = [_violation(title=f"Policy {i}") for i in range(7)]
        _, body = build_finding_briefing(_incident(), _result(violations=violations))
        for i in range(5):
            assert f"Policy {i}" in body
        assert "Policy 5" not in body
        assert "…and 2 more" in body

    def test_includes_confidence_percentage(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation(confidence=0.87)]))
        assert "87%" in body

    def test_includes_summary_when_present(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation()], summary="A clear match."))
        assert "A clear match." in body

    def test_omits_summary_section_when_empty(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation()], summary=""))
        assert body.count("\n\n\n") == 0

    def test_invites_a_reply_to_draft_and_names_hr_approval(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation()]))
        assert "draft a disciplinary action" in body
        assert "HR approval" in body

    def test_never_states_a_verdict(self):
        _, body = build_finding_briefing(_incident(), _result(violations=[_violation()]))
        for banned in ("terminate", "you should discipline", "this is a violation of law"):
            assert banned not in body.lower()
