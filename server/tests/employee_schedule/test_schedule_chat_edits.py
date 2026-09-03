"""schedule_chat's EDIT vocabulary — the coercer and the two pill renderers.

Pure: no DB, no Gemini. The resolver/executor need both and are covered by
the live dev-remote run documented in HUUME_SCHEDULE_EDITS_PLAN.md.

`coerce_edit_request` is the trust boundary for Stage A's output — the
model names an action and some hints, and everything downstream
(`_resolve_shift_ref`, `execute_edit_proposal`) assumes the shape is
already sane. An op that could never resolve is dropped HERE, so the
manager gets a clarify round rather than an opaque "couldn't find that
shift" after a pointless DB round-trip.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_schedule_chat_edits.py -q
"""

from datetime import datetime, timezone

import pytest

from app.matcha.services.scheduling.schedule_chat import (
    _coerce_delta, _parse_schedule_json, coerce_edit_request,
    edit_proposal_text, edit_result_text,
)


def _op(**over):
    base = {
        "kind": "reassign", "shift_id": "s1", "second_shift_id": None,
        "second_shift_role": None, "second_starts_at": None, "second_ends_at": None,
        "shift_role": "opener",
        "starts_at": "2026-08-12T08:00:00+00:00", "ends_at": "2026-08-12T16:00:00+00:00",
        "from_employee_name": "Cara Lopez", "to_employee_name": "Casey Nguyen",
        "new_starts_at": None, "new_ends_at": None, "advisories": [],
    }
    base.update(over)
    return base


class TestCoerceEditRequest:
    def test_unknown_kind_is_dropped(self):
        assert coerce_edit_request({"kind": "explode", "target_employee_name": "Cara"}) is None

    def test_non_dict_is_dropped(self):
        assert coerce_edit_request("reassign") is None

    def test_reassign_without_a_source_person_is_dropped(self):
        # "reassign to Casey" names no shift and no one losing it.
        assert coerce_edit_request({"kind": "reassign", "to_employee_name": "Casey"}) is None

    def test_reassign_without_a_destination_person_is_dropped(self):
        assert coerce_edit_request({"kind": "reassign", "target_employee_name": "Cara"}) is None

    def test_reassign_with_both_survives(self):
        out = coerce_edit_request(
            {"kind": "reassign", "target_employee_name": "Cara", "to_employee_name": "Casey"})
        assert out["kind"] == "reassign"
        assert (out["target_employee_name"], out["to_employee_name"]) == ("Cara", "Casey")

    def test_unassign_needs_the_person_coming_off(self):
        assert coerce_edit_request({"kind": "unassign", "target_role_hint": "opener"}) is None
        assert coerce_edit_request({"kind": "unassign", "target_employee_name": "Dana"}) is not None

    def test_retime_needs_some_new_time(self):
        assert coerce_edit_request({"kind": "retime", "target_role_hint": "opener"}) is None
        assert coerce_edit_request(
            {"kind": "retime", "target_role_hint": "opener", "new_start_time": "13:00"}) is not None

    def test_retime_accepts_a_relative_delta_alone(self):
        # "push the opener back an hour" gives no clock time at all.
        out = coerce_edit_request({"kind": "retime", "target_role_hint": "opener",
                                    "shift_by_minutes": 60})
        assert out is not None and out["shift_by_minutes"] == 60

    def test_cancel_needs_something_to_find_the_shift_by(self):
        assert coerce_edit_request({"kind": "cancel"}) is None
        assert coerce_edit_request({"kind": "cancel", "target_role_hint": "opener"}) is not None

    def test_swap_needs_a_hint_for_BOTH_shifts(self):
        assert coerce_edit_request({"kind": "swap", "target_role_hint": "opener"}) is None
        assert coerce_edit_request(
            {"kind": "swap", "target_role_hint": "opener", "second_role_hint": "closer"}) is not None

    def test_a_bad_date_is_nulled_not_fatal(self):
        out = coerce_edit_request({"kind": "cancel", "target_role_hint": "opener",
                                    "target_date": "next tuesday"})
        assert out is not None and out["target_date"] is None

    def test_a_real_date_survives(self):
        out = coerce_edit_request({"kind": "cancel", "target_date": "2026-08-12"})
        assert out["target_date"] == "2026-08-12"

    def test_free_text_hints_are_length_clamped(self):
        out = coerce_edit_request({"kind": "cancel", "target_role_hint": "x" * 500})
        assert len(out["target_role_hint"]) == 80

    def test_day_hints_carry_through_lowercased_and_clamped(self):
        out = coerce_edit_request({
            "kind": "cancel", "target_day_hint": "Tomorrow",
            "second_day_hint": "FRIDAY-WHATEVER-LONG", "new_day_hint": "wed",
        })
        assert out["target_day_hint"] == "tomorrow"
        assert out["second_day_hint"] == "friday-whate"  # 12-char cap
        assert out["new_day_hint"] == "wed"

    def test_missing_day_hints_are_none(self):
        out = coerce_edit_request({"kind": "cancel", "target_role_hint": "opener"})
        assert out["target_day_hint"] is None
        assert out["second_day_hint"] is None
        assert out["new_day_hint"] is None

    def test_cancel_survives_on_day_hint_alone(self):
        # "cancel tomorrow's shift" — no employee/role/exact-date, only a
        # relative day. Must not be dropped by the minimum-shape gate (a
        # real prod bug: this used to require target_date/target_role_hint/
        # target_employee_name and silently discarded a day-hint-only ask).
        out = coerce_edit_request({"kind": "cancel", "target_day_hint": "tomorrow"})
        assert out is not None

    def test_swap_survives_on_day_hints_alone(self):
        out = coerce_edit_request({
            "kind": "swap", "target_day_hint": "monday", "second_day_hint": "tuesday",
        })
        assert out is not None

    def test_retime_survives_on_new_day_hint_alone(self):
        out = coerce_edit_request({"kind": "retime", "target_role_hint": "opener", "new_day_hint": "friday"})
        assert out is not None

    @pytest.mark.parametrize("raw,expect", [
        ("unstaffed", "unstaffed"), ("open", "unstaffed"), ("empty", "unstaffed"),
        ("unassigned", "unstaffed"), ("Unstaffed", "unstaffed"),
        ("staffed", "staffed"), ("assigned", "staffed"), ("filled", "staffed"),
        ("busy", None), ("", None), (None, None),
    ])
    def test_target_staffing_hint_normalizes(self, raw, expect):
        out = coerce_edit_request({
            "kind": "cancel", "target_role_hint": "closer", "target_staffing_hint": raw,
        })
        assert out["target_staffing_hint"] == expect


class TestCoerceDelta:
    @pytest.mark.parametrize("value", [None, "60", True, 0, 721, -721])
    def test_rejected(self, value):
        # A delta past 12h means they meant a different DAY and should say so.
        assert _coerce_delta(value) is None

    @pytest.mark.parametrize("value,expect", [(60, 60), (-30, -30), (720, 720), (90.0, 90)])
    def test_accepted(self, value, expect):
        assert _coerce_delta(value) == expect


class TestParseDiscriminator:
    def test_edit_action_survives_the_json_parse(self):
        data = _parse_schedule_json(
            '{"actionable": true, "ack": "ok", "action": "edit", "edit_requests": '
            '[{"kind": "reassign", "target_employee_name": "Cara", "to_employee_name": "Casey"}]}')
        assert data["action"] == "edit" and data["actionable"] is True
        assert len(data["edit_requests"]) == 1

    def test_edit_action_with_no_usable_op_is_not_actionable(self):
        # Every op was dropped by the coercer -> nothing to propose. The
        # caller falls back to logging the message as an EMS event.
        data = _parse_schedule_json(
            '{"actionable": true, "ack": "ok", "action": "edit", "edit_requests": '
            '[{"kind": "reassign", "to_employee_name": "Casey"}]}')
        assert data["actionable"] is False

    def test_edit_label_without_edit_ops_falls_back_to_create(self):
        data = _parse_schedule_json(
            '{"actionable": true, "ack": "ok", "action": "edit", "shift_requests": '
            '[{"label": "opener", "start_time": "08:00", "end_time": "16:00"}]}')
        assert data["action"] == "create"

    def test_create_stays_the_default_when_action_is_absent(self):
        data = _parse_schedule_json(
            '{"actionable": true, "ack": "ok", "shift_requests": '
            '[{"label": "opener", "start_time": "08:00", "end_time": "16:00"}]}')
        assert data["action"] == "create" and data["actionable"] is True


class TestEditProposalText:
    def test_reassign_line_names_both_people(self):
        text = edit_proposal_text({"ack": "Got it.", "ops": [_op()]})
        assert "Cara Lopez → Casey Nguyen" in text
        assert "Reply **confirm**" in text

    def test_advisories_are_rendered_verbatim_with_the_statute(self):
        text = edit_proposal_text({"ack": "Got it.", "ops": [_op(advisories=[
            {"message": "a 30-min meal break is required", "statute": "Cal. Lab. Code § 512"}])]})
        assert "Heads up on Casey Nguyen: a 30-min meal break is required (Cal. Lab. Code § 512)" in text

    def test_retime_shows_the_new_window(self):
        text = edit_proposal_text({"ack": "ok", "ops": [_op(
            kind="retime", from_employee_name=None, to_employee_name=None,
            new_starts_at="2026-08-12T13:00:00+00:00",
            new_ends_at="2026-08-12T21:00:00+00:00")]})
        assert "13:00–21:00" in text

    def test_swap_names_both_shifts(self):
        text = edit_proposal_text({"ack": "ok", "ops": [_op(
            kind="swap", second_shift_id="s2", second_shift_role="closer",
            second_starts_at="2026-08-12T14:00:00+00:00",
            second_ends_at="2026-08-12T22:00:00+00:00")]})
        assert "**Opener**" in text and "**Closer**" in text

    def test_cancel_and_unassign_read_as_actions(self):
        assert "cancel" in edit_proposal_text({"ack": "ok", "ops": [_op(kind="cancel")]})
        assert "remove Cara Lopez" in edit_proposal_text(
            {"ack": "ok", "ops": [_op(kind="unassign", to_employee_name=None)]})


class TestEditResultText:
    def test_success_carries_the_deep_link_token(self):
        text = edit_result_text([{**_op(), "ok": True}])
        # The one markup construct systemContent.tsx parses alongside **bold**.
        assert "[[shift:s1:2026-08-12]]" in text
        assert "1 change is live" in text

    def test_a_failed_op_is_named_with_its_reason_not_swallowed(self):
        text = edit_result_text([
            {**_op(), "ok": True},
            {**_op(kind="unassign", from_employee_name="Dana Kim", to_employee_name=None),
             "ok": False, "reason": "that shift was cancelled"},
        ])
        assert "1 change is live" in text
        assert "Couldn't change Dana Kim on **Opener** [[shift:s1:2026-08-12]]: that shift was cancelled" in text

    def test_all_failed_says_so_plainly(self):
        text = edit_result_text([{**_op(), "ok": False, "reason": "they picked up a conflict"}])
        assert "Couldn't make any of those changes." in text
        assert "[[shift:s1:2026-08-12]]" in text

    def test_bulk_failures_identify_each_shift_and_its_actual_reason(self):
        text = edit_result_text([
            {**_op(kind="assign", from_employee_name=None, to_employee_name="Ellie Marsh"),
             "ok": False, "reason": "they picked up a conflicting shift in the meantime"},
            {**_op(
                kind="assign", shift_id="s2", shift_role="closer",
                starts_at="2026-08-13T17:00:00+00:00",
                from_employee_name=None, to_employee_name="Ellie Marsh",
            ), "ok": False, "reason": "Food Handler Card requires an approved credential document before scheduling."},
        ])

        assert "[[shift:s1:2026-08-12]]: they picked up a conflicting shift" in text
        assert "[[shift:s2:2026-08-13]]: Food Handler Card requires an approved" in text

    def test_plural_agreement(self):
        text = edit_result_text([{**_op(), "ok": True}, {**_op(shift_id="s2"), "ok": True}])
        assert "2 changes are live" in text
