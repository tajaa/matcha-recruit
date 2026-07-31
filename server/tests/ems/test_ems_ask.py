"""Channel-answer redaction + the deterministic (no-Gemini) replies.

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
        assert "Events" in text

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
        # The Events tab is admin-only (routes/ems.py) — pointing an
        # employee at a 403 is worse than not mentioning it.
        assert "promote" not in ask.help_text(is_admin=False).lower()

    def test_admin_help_mentions_promotion(self):
        assert "promote" in ask.help_text(is_admin=True).lower()

    def test_no_markdown_emphasis(self):
        # MessageList parses `**` pairs; a stray asterisk eats the rest of
        # the pill as emphasis.
        for is_admin in (True, False):
            assert "*" not in ask.help_text(is_admin=is_admin)


class TestAnswerQuestion:
    @pytest.mark.asyncio
    async def test_gemini_failure_degrades_to_a_pointer(self, monkeypatch):
        from app.matcha.services.ems import event_intake

        def _boom():
            raise RuntimeError("Gemini unavailable")
        # Patch the module that DEFINES _get_client (ask.py imports it
        # lazily from event_intake), per the repo's patching rule.
        monkeypatch.setattr(event_intake, "_get_client", _boom)

        text = await ask.answer_question("what happened?", [_event()], is_admin=False)
        assert "couldn't pull that up" in text
        assert text.startswith("\U0001F4CB")

    @pytest.mark.asyncio
    async def test_model_asterisks_and_clarify_marker_stripped(self, monkeypatch):
        from app.matcha.services.ems import event_intake

        class _Resp:
            text = "Couple things: **freezer** ran warm \U0001F914 and a guest slipped."

        class _Models:
            async def generate_content(self, **kwargs):
                return _Resp()

        class _Aio:
            models = _Models()

        class _Client:
            aio = _Aio()

        monkeypatch.setattr(event_intake, "_get_client", lambda: _Client())

        text = await ask.answer_question("what happened?", [_event()], is_admin=True)
        assert "*" not in text
        # 🤔 is the armed-clarify marker; a reply to an ANSWER pill has no
        # event to claim, so the model must never be able to render one.
        assert "\U0001F914" not in text
        assert "freezer" in text
