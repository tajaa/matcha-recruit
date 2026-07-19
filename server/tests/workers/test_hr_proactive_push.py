"""HR Pilot proactive push — pure-function tests (no DB, no Celery execution).

The worker's DB paths are verified manually (repo convention for workers). What
is tested here is everything that decides WHAT gets said and WHETHER it fires
twice — the parts that are wrong silently.
"""

import re
from datetime import date, datetime, timedelta

import pytest

from app.workers.tasks.hr_proactive_push import (
    MAX_DIGEST_NAMES,
    build_discipline_briefing,
    build_leave_return_briefing,
    build_signature_digest_briefing,
    discipline_kinds_in_window,
    hr_pilot_enabled,
)

TODAY = date(2026, 7, 20)
HORIZON = TODAY + timedelta(days=7)

# The FE renumberer rewrites `[ns:id]` markers into `[1]`-style footnote markers.
# A briefing that happens to contain that shape would be mangled on render.
_CITATION_SHAPE = re.compile(
    r"\[(profile|law|handbook|policy|playbook|floor|ladder|schedule|training|incident)"
    r"(:[^\]\s]+)?\]"
)


# --------------------------------------------------------------------------- #
# Leave-return briefing
# --------------------------------------------------------------------------- #

def _leave(leave_type="fmla", first="Jane", last="Doe"):
    return {"first_name": first, "last_name": last, "leave_type": leave_type,
            "return_date": date(2026, 7, 27)}


def test_leave_briefing_states_who_and_when():
    title, body = build_leave_return_briefing(_leave())
    assert "Jane Doe" in title
    assert "Monday" in title  # 2026-07-27 is a Monday
    assert "Jane Doe" in body
    assert "Monday" in body


def test_fmla_return_carries_reinstatement_and_antiretaliation():
    """The legal substance of an FMLA return is the whole reason to push it."""
    _, body = build_leave_return_briefing(_leave("fmla"))
    assert "equivalent" in body
    assert "cannot count against them" in body


def test_non_fmla_leave_omits_the_fmla_paragraph():
    _, body = build_leave_return_briefing(_leave("bereavement"))
    assert "equivalent" not in body


def test_every_leave_briefing_warns_off_medical_questions():
    for lt in ("fmla", "bereavement", "military", "unpaid_loa"):
        _, body = build_leave_return_briefing(_leave(lt))
        assert "medical condition" in body
        assert "corporate HR" in body


def test_leave_briefing_handles_missing_name_and_date():
    title, body = build_leave_return_briefing(
        {"leave_type": "fmla", "first_name": None, "last_name": None, "return_date": None})
    assert "an employee" in title or "an employee" in body
    assert "unspecified" in body


# --------------------------------------------------------------------------- #
# Discipline briefing
# --------------------------------------------------------------------------- #

def _disc(**over):
    row = {"first_name": "Sam", "last_name": "Ito", "discipline_type": "written_warning",
           "expires_at": datetime(2026, 7, 24), "review_date": date(2026, 7, 22),
           "expected_improvement": "On time for every shift for 30 days"}
    row.update(over)
    return row


def test_review_briefing_is_about_the_check_in():
    title, body = build_discipline_briefing(_disc(), "discipline_review")
    assert "check-in" in title.lower()
    assert "On time for every shift for 30 days" in body
    assert "contemporaneous" in body


def test_expiry_briefing_warns_against_reusing_a_lapsed_record():
    title, body = build_discipline_briefing(_disc(), "discipline_expiry")
    assert "expires" in title.lower()
    assert "expired record" in body


def test_both_discipline_briefings_route_termination_to_hr():
    for kind in ("discipline_review", "discipline_expiry"):
        _, body = build_discipline_briefing(_disc(), kind)
        assert "termination" in body
        assert "corporate HR" in body


def test_review_briefing_without_expected_improvement():
    _, body = build_discipline_briefing(_disc(expected_improvement=None), "discipline_review")
    assert "improvement this record asked for" not in body


# --------------------------------------------------------------------------- #
# Signature digest
# --------------------------------------------------------------------------- #

def _docs(n):
    return [{"first_name": f"E{i}", "last_name": "X", "title": "Employee Handbook"}
            for i in range(n)]


def test_digest_counts_and_lists():
    title, body = build_signature_digest_briefing(_docs(3), 7)
    assert title.startswith("3 unreturned")
    assert body.count("- E") == 3


def test_digest_singular_plural():
    assert build_signature_digest_briefing(_docs(1), 7)[0] == "1 unreturned acknowledgement"
    assert "2 unreturned acknowledgements" in build_signature_digest_briefing(_docs(2), 7)[0]


def test_digest_caps_names_and_says_so():
    """A truncated list the reader takes as complete is the failure mode."""
    n = MAX_DIGEST_NAMES + 5
    _, body = build_signature_digest_briefing(_docs(n), 7)
    assert body.count("- E") == MAX_DIGEST_NAMES
    assert f"...and {n - MAX_DIGEST_NAMES} more" in body


def test_digest_explains_why_it_matters():
    _, body = build_signature_digest_briefing(_docs(2), 7)
    assert "communicated" in body


# --------------------------------------------------------------------------- #
# No briefing may look like a citation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("title,body", [
    build_leave_return_briefing(_leave("fmla")),
    build_leave_return_briefing(_leave("bereavement")),
    build_discipline_briefing(_disc(), "discipline_review"),
    build_discipline_briefing(_disc(), "discipline_expiry"),
    build_signature_digest_briefing(_docs(3), 7),
])
def test_briefings_contain_no_citation_shaped_brackets(title, body):
    """The FE rewrites `[ns:id]` markers into footnote numbers. A briefing that
    accidentally contains that shape would render mangled."""
    assert not _CITATION_SHAPE.search(title)
    assert not _CITATION_SHAPE.search(body)


# --------------------------------------------------------------------------- #
# Trigger-window math
# --------------------------------------------------------------------------- #

def test_row_matching_only_review_does_not_fire_expiry():
    """The SQL matches `review_date OR expires_at`, so a row can arrive having
    matched on one date while the other is months away. Re-checking each date is
    what stops a check-in reminder from also announcing a distant expiry."""
    row = {"review_date": date(2026, 7, 22), "expires_at": datetime(2027, 1, 1)}
    assert discipline_kinds_in_window(row, TODAY, HORIZON) == ["discipline_review"]


def test_row_matching_only_expiry_does_not_fire_review():
    row = {"review_date": date(2025, 1, 1), "expires_at": datetime(2026, 7, 24)}
    assert discipline_kinds_in_window(row, TODAY, HORIZON) == ["discipline_expiry"]


def test_row_hitting_both_fires_both():
    row = {"review_date": date(2026, 7, 22), "expires_at": datetime(2026, 7, 24)}
    assert discipline_kinds_in_window(row, TODAY, HORIZON) == [
        "discipline_review", "discipline_expiry"]


def test_nulls_fire_nothing():
    assert discipline_kinds_in_window({"review_date": None, "expires_at": None},
                                      TODAY, HORIZON) == []
    assert discipline_kinds_in_window({}, TODAY, HORIZON) == []


def test_window_boundaries_are_inclusive():
    assert discipline_kinds_in_window({"expires_at": TODAY}, TODAY, HORIZON) == ["discipline_expiry"]
    assert discipline_kinds_in_window({"expires_at": HORIZON}, TODAY, HORIZON) == ["discipline_expiry"]
    assert discipline_kinds_in_window({"expires_at": HORIZON + timedelta(days=1)},
                                      TODAY, HORIZON) == []


# --------------------------------------------------------------------------- #
# Feature resolution
# --------------------------------------------------------------------------- #

def test_hr_pilot_off_by_default():
    assert hr_pilot_enabled({}, "bespoke") is False


def test_hr_pilot_on_when_stored():
    assert hr_pilot_enabled({"hr_pilot": True}, "bespoke") is True


def test_hr_pilot_accepts_json_string_column():
    assert hr_pilot_enabled('{"hr_pilot": true}', "bespoke") is True


def test_hr_pilot_is_not_bundled_in_any_tier():
    """Documents the current packaging: hr_pilot is sold per-company, not
    granted by a tier overlay. If this ever fails, the flag has been bundled —
    which is exactly the case the Python-side merge in `hr_pilot_enabled`
    exists to keep working (a SQL `->> 'hr_pilot'` check would start silently
    skipping the newly-entitled companies)."""
    from app.core.feature_flags import TIER_REQUIRED_FEATURES
    bundled = [t for t, flags in TIER_REQUIRED_FEATURES.items() if "hr_pilot" in (flags or {})]
    assert bundled == [], f"hr_pilot is now bundled in {bundled} — see hr_pilot_enabled"


def test_overlay_granted_flag_resolves_without_being_stored():
    """The merge honours a tier overlay even when enabled_features is empty —
    the property `hr_pilot_enabled` relies on."""
    from app.core.feature_flags import TIER_REQUIRED_FEATURES, merge_company_features
    overlay = TIER_REQUIRED_FEATURES.get("matcha_x") or {}
    granted = [k for k, v in overlay.items() if v]
    if not granted:
        pytest.skip("no positively-granted flags in the matcha_x overlay")
    assert merge_company_features({}, "matcha_x").get(granted[0]) is True


def test_hr_pilot_tolerates_null_column():
    assert hr_pilot_enabled(None, None) is False
