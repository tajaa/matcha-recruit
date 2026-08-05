"""Pure, DB-free rules for the @huume channel-scheduling flow — no DB, no
Gemini. Mirrors tests/employee_schedule/test_schedule_rules.py's style.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_rules.py -q
"""

from datetime import date

import pytest

from app.matcha.services.scheduling.schedule_chat_rules import (
    CandidateContext,
    NeedsClarify,
    apply_channel_default_location,
    build_adhoc_spec,
    match_location,
    match_template,
    parse_confirm_reply,
    parse_time_hint,
    rank_candidates,
    resolve_clarify_answer,
    resolve_dates,
    resolve_week,
)

LOCATIONS = [
    {"id": "1", "name": "La Jolla Studio", "address": "7863 Girard Ave",
     "city": "San Diego", "state": "CA", "zipcode": "92037"},
    {"id": "2", "name": "Downtown A", "address": "100 Main St",
     "city": "San Diego", "state": "CA", "zipcode": "92101"},
    {"id": "3", "name": "Downtown B", "address": "200 Main St",
     "city": "San Diego", "state": "CA", "zipcode": "92101"},
]

TEMPLATES = [
    {"id": "t1", "name": "Opening Shift", "role": "Front Desk"},
    {"id": "t2", "name": "Closer", "role": "Closer"},
]


class TestResolveWeek:
    def test_this_week_wednesday(self):
        wed = date(2026, 8, 5)
        assert resolve_week(None, wed) == date(2026, 8, 2)  # the preceding Sunday

    def test_next_week_wednesday(self):
        wed = date(2026, 8, 5)
        assert resolve_week("next_week", wed) == date(2026, 8, 9)

    def test_this_week_when_today_is_sunday(self):
        sun = date(2026, 8, 2)
        assert resolve_week(None, sun) == sun

    def test_next_week_when_today_is_sunday_is_not_today(self):
        # A Sunday's OWN week-start is itself; "next_week" must still be a
        # full week out, never today.
        sun = date(2026, 8, 2)
        assert resolve_week("next_week", sun) == date(2026, 8, 9)

    def test_this_week_alias(self):
        wed = date(2026, 8, 5)
        assert resolve_week("this_week", wed) == resolve_week(None, wed)


class TestResolveDates:
    WEEK_START = date(2026, 8, 2)  # a Sunday
    TODAY = date(2026, 8, 1)

    def test_explicit_date_wins(self):
        out = resolve_dates({"date": "2026-08-10"}, self.WEEK_START, self.TODAY)
        assert out == [date(2026, 8, 10)]

    def test_explicit_date_outside_week_still_used(self):
        out = resolve_dates({"date": "2026-08-20"}, self.WEEK_START, self.TODAY)
        assert out == [date(2026, 8, 20)]

    def test_named_weekdays_within_week(self):
        out = resolve_dates({"weekdays": ["monday", "friday"]}, self.WEEK_START, self.TODAY)
        assert out == [date(2026, 8, 3), date(2026, 8, 7)]

    def test_template_mask_fallback(self):
        out = resolve_dates({}, self.WEEK_START, self.TODAY, template_days=[1, 2, 3, 4, 5, 6])
        assert out == [
            date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5),
            date(2026, 8, 6), date(2026, 8, 7), date(2026, 8, 8),
        ]

    def test_no_signal_needs_clarify(self):
        out = resolve_dates({}, self.WEEK_START, self.TODAY)
        assert isinstance(out, NeedsClarify)

    def test_all_past_dates_need_clarify(self):
        out = resolve_dates({"date": "2026-07-01"}, self.WEEK_START, self.TODAY)
        assert isinstance(out, NeedsClarify)

    def test_past_day_in_this_week_dropped(self):
        # today is a Wednesday inside this same week; Monday has already
        # passed, so only forward days survive.
        today = date(2026, 8, 5)
        out = resolve_dates({"weekdays": ["monday", "friday"]}, self.WEEK_START, today)
        assert out == [date(2026, 8, 7)]

    def test_bare_weekday_all_past_rolls_to_next_week(self):
        # "Monday" said on a Saturday, with no explicit week hint: every
        # candidate in the resolved (this) week is already past, so this
        # rolls forward to the SAME weekday next week rather than clarifying
        # — a manager saying "Monday" virtually always means the next one.
        today = date(2026, 8, 8)
        out = resolve_dates({"weekdays": ["monday"]}, self.WEEK_START, today)
        assert out == [date(2026, 8, 10)]

    def test_explicit_past_date_still_needs_clarify(self):
        # An explicit ISO date has no unambiguous "next" — unlike a bare
        # weekday name, this still clarifies rather than guessing a week.
        today = date(2026, 8, 8)
        out = resolve_dates({"date": "2026-08-03"}, self.WEEK_START, today)
        assert isinstance(out, NeedsClarify)


class TestMatchLocation:
    def test_la_jolla_matches_by_name_not_city(self):
        out = match_location("la jolla", LOCATIONS)
        assert [l["id"] for l in out] == ["1"]

    def test_downtown_tie_returns_both(self):
        out = match_location("downtown", LOCATIONS)
        assert {l["id"] for l in out} == {"2", "3"}

    def test_no_match_returns_empty(self):
        assert match_location("nowhereville", LOCATIONS) == []

    def test_empty_hint_single_location_shortcut(self):
        out = match_location(None, LOCATIONS[:1])
        assert [l["id"] for l in out] == ["1"]

    def test_empty_hint_multiple_locations_returns_empty(self):
        assert match_location(None, LOCATIONS[:2]) == []

    def test_empty_hint_no_locations_returns_empty(self):
        assert match_location(None, []) == []

    def test_empty_hint_empty_string(self):
        out = match_location("", LOCATIONS[:1])
        assert [l["id"] for l in out] == ["1"]


class TestResolveClarifyAnswer:
    OPTS1 = ["Sunset Smile Dental — Wilshire (Los Angeles)"]
    OPTS2 = [
        "Sunset Smile Dental — Wilshire (Los Angeles)",
        "Sunset Smile Dental — La Jolla (San Diego)",
    ]

    def test_affirmative_single_option_snaps_and_strips_city(self):
        assert resolve_clarify_answer("Yes", self.OPTS1) == "Sunset Smile Dental — Wilshire"

    def test_affirmative_two_options_unchanged(self):
        assert resolve_clarify_answer("yes", self.OPTS2) == "yes"

    def test_unique_containment_match_snaps(self):
        assert resolve_clarify_answer("wilshire", self.OPTS2) == "Sunset Smile Dental — Wilshire"

    def test_ambiguous_containment_unchanged(self):
        assert resolve_clarify_answer("sunset smile", self.OPTS2) == "sunset smile"

    def test_affirmative_plus_extra_text_uses_containment_path(self):
        assert resolve_clarify_answer("Yes, wilshire", self.OPTS1) == "Sunset Smile Dental — Wilshire"

    def test_no_options_passthrough(self):
        assert resolve_clarify_answer("8am to 4pm", []) == "8am to 4pm"


class TestMatchTemplate:
    def test_opener_matches_opening_shift_by_name_stem(self):
        assert match_template("opener", None, TEMPLATES)["id"] == "t1"

    def test_closer_matches_by_role_stem(self):
        assert match_template("closer", None, TEMPLATES)["id"] == "t2"

    def test_none_hint_falls_back_to_label(self):
        assert match_template(None, "opener", TEMPLATES)["id"] == "t1"

    def test_no_match_returns_none(self):
        assert match_template("dishwasher", None, TEMPLATES) is None

    def test_exact_name_beats_stem_match(self):
        templates = [
            {"id": "a", "name": "Closer", "role": "Front Desk"},
            {"id": "b", "name": "Weekend Closing", "role": "Closer"},
        ]
        assert match_template("closer", None, templates)["id"] == "a"

    def test_empty_hint_and_label_returns_none(self):
        assert match_template(None, None, TEMPLATES) is None

    def test_no_templates_returns_none(self):
        assert match_template("opener", None, []) is None


class TestBuildAdhocSpec:
    def test_break_minutes_is_zero(self):
        from datetime import time
        spec = build_adhoc_spec("opener", time(6, 0), time(14, 0), "Front Desk")
        assert spec["break_minutes"] == 0
        assert spec["template_id"] is None
        assert spec["label"] == "opener"
        assert spec["role"] == "Front Desk"


def _ctx(eid, name, job_title="Front Desk", conflicts=None, violations=None, week_hours=0.0):
    return CandidateContext(
        employee_id=eid, name=name, job_title=job_title,
        conflicts=conflicts or [], violations=violations or [], week_hours=week_hours,
    )


class TestRankCandidates:
    def test_block_violation_excluded(self):
        blocked = _ctx("e1", "Riley Soto", violations=[
            {"severity": "block", "message": "minor cap", "statute": "Cal. Lab. Code § 1391"},
        ])
        clean = _ctx("e2", "Marcus Bell")
        result = rank_candidates(1, [blocked, clean])
        assert [c.employee_id for c in result.chosen] == ["e2"]
        assert len(result.excluded) == 1
        excluded_ctx, reason = result.excluded[0]
        assert excluded_ctx.employee_id == "e1"
        assert "minor cap" in reason and "Cal. Lab. Code § 1391" in reason

    def test_conflict_excluded(self):
        conflicted = _ctx("e1", "Busy Bea", conflicts=[
            {"shift_id": "s1", "starts_at": "x", "ends_at": "y", "role": "Server", "status": "published"},
        ])
        clean = _ctx("e2", "Free Fred")
        result = rank_candidates(1, [conflicted, clean])
        assert [c.employee_id for c in result.chosen] == ["e2"]
        assert result.excluded[0][0].employee_id == "e1"

    def test_zero_advisory_sorts_before_one_advisory(self):
        with_advisory = _ctx("e1", "A", violations=[{"severity": "advisory", "message": "m", "statute": None}])
        clean = _ctx("e2", "B")
        result = rank_candidates(2, [with_advisory, clean])
        assert [c.employee_id for c in result.chosen] == ["e2", "e1"]

    def test_fewer_week_hours_sorts_first(self):
        busy = _ctx("e1", "A", week_hours=38.0)
        light = _ctx("e2", "B", week_hours=10.0)
        result = rank_candidates(1, [busy, light])
        assert [c.employee_id for c in result.chosen] == ["e2"]

    def test_pinned_sorts_ahead_of_cleaner_unpinned(self):
        pinned = _ctx("e1", "Named Nancy", violations=[
            {"severity": "advisory", "message": "m", "statute": None},
        ])
        cleaner = _ctx("e2", "Anyone Else")
        result = rank_candidates(1, [pinned, cleaner], pinned_ids=["e1"])
        assert [c.employee_id for c in result.chosen] == ["e1"]

    def test_pinned_with_block_still_excluded(self):
        pinned_but_blocked = _ctx("e1", "Riley Soto", violations=[
            {"severity": "block", "message": "minor cap", "statute": "Cal. Lab. Code § 1391"},
        ])
        result = rank_candidates(1, [pinned_but_blocked], pinned_ids=["e1"])
        assert result.chosen == []
        assert result.excluded[0][0].employee_id == "e1"

    def test_deterministic_tie_by_name_then_id(self):
        a = _ctx("z9", "Same Name")
        b = _ctx("a1", "Same Name")
        result = rank_candidates(2, [a, b])
        assert [c.employee_id for c in result.chosen] == ["a1", "z9"]

    def test_alternates_hold_the_overflow(self):
        c1, c2, c3 = _ctx("e1", "A"), _ctx("e2", "B"), _ctx("e3", "C")
        result = rank_candidates(1, [c1, c2, c3])
        assert len(result.chosen) == 1
        assert len(result.alternates) == 2


class TestParseConfirmReply:
    @pytest.mark.parametrize("text", [
        "confirm", "confirmed", "yes", "yep", "do it", "go ahead",
        "approved", "book it", "ship it", "lgtm", "looks good", "sounds good",
    ])
    def test_confirm_variants(self, text):
        assert parse_confirm_reply(text) == "confirm"

    @pytest.mark.parametrize("text", [
        "cancel", "no", "nope", "nah", "never mind", "forget it", "don't",
    ])
    def test_cancel_variants(self, text):
        assert parse_confirm_reply(text) == "cancel"

    def test_thumbs_up_confirms(self):
        assert parse_confirm_reply("\U0001F44D") == "confirm"

    def test_unrelated_text_is_other(self):
        assert parse_confirm_reply("make it 8am instead") == "other"

    def test_conflicting_reply_is_other_not_leading_token(self):
        # Matching only the leading token used to read this as "cancel" —
        # an ambiguous message with trailing content must not silently pick
        # either interpretation; it falls to "other" and re-arms for a
        # clean confirm/cancel.
        assert parse_confirm_reply("no wait confirm") == "other"

    def test_partial_confirm_with_modification_is_other(self):
        # A real production bug: "yes but swap Dana for Marcus" must never
        # execute the unmodified proposal.
        assert parse_confirm_reply("yes but swap Dana for Marcus") == "other"

    def test_empty_string_is_other(self):
        assert parse_confirm_reply("") == "other"


LOC_A = {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "Wilshire", "city": "LA"}
LOC_B = {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "name": "Sunset", "city": "LA"}


class TestApplyChannelDefaultLocation:
    def test_unscoped_channel_is_a_noop(self):
        assert apply_channel_default_location([], None, None, [LOC_A, LOC_B]) == []

    def test_channel_default_resolves_without_a_hint(self):
        # Both empty-hint outcomes (0 matches and >1 matches) collapse to
        # the channel's own store — this is the clarify round being skipped.
        assert apply_channel_default_location([], "", LOC_B["id"], [LOC_A, LOC_B]) == [LOC_B]
        assert apply_channel_default_location([LOC_A, LOC_B], None, LOC_B["id"], [LOC_A, LOC_B]) == [LOC_B]

    def test_explicit_hint_always_wins(self):
        # "unless asked otherwise": a hint naming the OTHER store is honored.
        matched = [LOC_A]
        assert apply_channel_default_location(matched, "wilshire", LOC_B["id"], [LOC_A, LOC_B]) is matched

    def test_stale_channel_location_falls_through(self):
        # Deactivated store: absent from the active list → normal clarify path.
        matched = [LOC_A, LOC_B]
        assert apply_channel_default_location(
            matched, "", "cccccccc-cccc-cccc-cccc-cccccccccccc", [LOC_A, LOC_B],
        ) is matched

    def test_uuid_vs_str_id_comparison(self):
        from uuid import UUID
        assert apply_channel_default_location([], "", UUID(LOC_B["id"]), [LOC_A, LOC_B]) == [LOC_B]


class TestParseTimeHint:
    """The "8am shift" disambiguator — narrows _resolve_shift_ref's
    ambiguous-match listing by hour when the manager gave a time hint."""

    @pytest.mark.parametrize("hint,expect", [
        ("8am", (8, 0)),
        ("8 am", (8, 0)),
        ("12am", (0, 0)),
        ("12pm", (12, 0)),
        ("8:30pm", (20, 30)),
        ("8:30 PM", (20, 30)),
        ("08:00", (8, 0)),
        ("20:00", (20, 0)),
    ])
    def test_parses_unambiguous_forms(self, hint, expect):
        result = parse_time_hint(hint)
        assert result is not None
        assert (result.hour, result.minute) == expect

    @pytest.mark.parametrize("hint", [None, "", "8", "morning", "the opener", "13am"])
    def test_ambiguous_or_empty_returns_none(self, hint):
        assert parse_time_hint(hint) is None
