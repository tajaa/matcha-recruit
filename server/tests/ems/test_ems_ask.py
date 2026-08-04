"""Channel-answer redaction + the deterministic (no-Gemini) replies — the
pure pieces `ask.py` still owns after the model-facing answer loop moved to
`channel_agent.py` (see tests/ems/test_channel_agent.py for that half).

Every REST read of ems_events is admin-only; a channel answer is broadcast
to the whole room, employees included. These tests pin the difference —
see services/ems/ask.py's module docstring.

    cd server && ./venv/bin/python -m pytest tests/ems/test_ems_ask.py -q
"""

from datetime import datetime, timezone

import pytest

from app.matcha.services.ems import ask


def _event(**over):
    base = {
        "title": "Walk-in freezer running warm",
        "category": "equipment",
        "severity_hint": "medium",
        "doc": {"asset": "walk-in freezer", "issue": "48 degrees"},
        "narrative": "the walk-in is at 48",
        "incident_recommendation": True,
        "status": "logged",
        "incident_id": None,
        "created_at": datetime(2026, 7, 14, tzinfo=timezone.utc),
    }
    base.update(over)
    return base


class TestIsAdminRole:
    @pytest.mark.parametrize("role", ["client", "admin"])
    def test_admin_roles(self, role):
        assert ask.is_admin_role(role) is True

    @pytest.mark.parametrize("role", ["employee", "candidate", "individual", "creator", None])
    def test_everyone_else(self, role):
        assert ask.is_admin_role(role) is False


class TestRenderEventsBlock:
    def test_employee_view_omits_matchas_assessment(self):
        # severity / incident flag / extracted doc are Matcha's read on the
        # event, not the reporter's words — admin only.
        block = ask.render_events_block([_event()], is_admin=False)
        assert "Walk-in freezer running warm" in block
        assert "Equipment" in block
        assert "severity" not in block
        assert "incident review" not in block
        assert "48 degrees" not in block

    def test_admin_view_carries_assessment(self):
        block = ask.render_events_block([_event()], is_admin=True)
        assert "severity medium" in block
        assert "flagged for possible incident review" in block
        assert "48 degrees" in block

    def test_promoted_shown_to_everyone(self):
        # That something became a formal incident is a fact about the
        # record, not an assessment — and the room usually watched it happen.
        block = ask.render_events_block([_event(status="promoted")], is_admin=False)
        assert "promoted to a formal incident" in block

    def test_promoted_event_not_double_flagged_for_admin(self):
        block = ask.render_events_block([_event(status="promoted")], is_admin=True)
        assert "promoted to a formal incident" in block
        assert "flagged for possible incident review" not in block

    def test_empty_is_explicit(self):
        assert ask.render_events_block([], is_admin=True) == "(nothing logged in this channel)"

    def test_filtered_empty_does_not_claim_the_room_is_clean(self):
        # `filtered=True` means this channel HAS events, they're just
        # hidden from this asker (e.g. a non-admin's behavioral filter) —
        # rendering the plain empty string here would let the model tell
        # the room "nothing's been logged", a false statement about the
        # record. See the docstring on render_events_block for the pairing
        # with ask.no_events_text's own filtered/unfiltered split.
        block = ask.render_events_block([], is_admin=False, filtered=True)
        assert block != "(nothing logged in this channel)"
        assert "may see more" in block

    def test_filtered_is_irrelevant_when_events_exist(self):
        block = ask.render_events_block([_event()], is_admin=False, filtered=True)
        assert "Walk-in freezer running warm" in block

    def test_missing_title_does_not_crash(self):
        block = ask.render_events_block([_event(title=None)], is_admin=False)
        assert "Untitled" in block

    def test_non_dict_doc_ignored(self):
        block = ask.render_events_block([_event(doc="not a dict")], is_admin=True)
        assert "Walk-in freezer" in block


class TestNoEventsText:
    def test_filtered_does_not_claim_the_record_is_clean(self):
        # An employee whose only channel event is `behavioral` must not be
        # told nothing was reported — that's a false statement about the
        # record, and it points at the wrong next step.
        text = ask.no_events_text(filtered=True)
        assert "Nothing's been logged" not in text
        assert "Ops" in text

    def test_unfiltered_invites_a_report(self):
        text = ask.no_events_text(filtered=False)
        assert "Nothing's been logged in this channel yet" in text


class TestHelpText:
    def test_lists_the_three_channel_capabilities(self):
        text = ask.help_text(is_admin=False)
        assert "Log anything" in text
        assert "what's been logged" in text
        assert "reply" in text.lower()

    def test_employee_help_omits_the_events_tab(self):
        # The Events tab (now under the "Ops" sidebar group) is admin-only
        # (routes/ems.py) — pointing an employee at a 403 is worse than not
        # mentioning it.
        assert "promote" not in ask.help_text(is_admin=False).lower()

    def test_admin_help_mentions_promotion(self):
        assert "promote" in ask.help_text(is_admin=True).lower()

    def test_no_markdown_emphasis(self):
        # MessageList parses `**` pairs; a stray asterisk eats the rest of
        # the pill as emphasis.
        for is_admin in (True, False):
            assert "*" not in ask.help_text(is_admin=is_admin)

    def test_extra_lines_are_inserted(self):
        text = ask.help_text(is_admin=False, extra_lines=("• Answer stock questions",))
        assert "Answer stock questions" in text

    def test_no_extra_lines_is_unchanged(self):
        assert ask.help_text(is_admin=False, extra_lines=()) == ask.help_text(is_admin=False)
