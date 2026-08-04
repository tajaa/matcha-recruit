"""Intent fork for "@huume ..." channel messages.

The asymmetry under test: a question mistakenly LOGGED is visible and
dismissable in the Events tab; an event mistakenly read as a question is
gone, because nobody re-types it. So the log-side cases below are the
load-bearing ones — they pin phrasings that LOOK interrogative but are
reports.

    cd server && ./venv/bin/python -m pytest tests/ems/test_ems_intent.py -q
"""

import pytest

from app.matcha.services.ems.intent import ASK, HELP, LINK, LOG, classify_intent, strip_mention


class TestStripMention:
    @pytest.mark.parametrize("raw,expected", [
        ("@huume the ice machine is out", "the ice machine is out"),
        ("@Huume: freezer at 48", "freezer at 48"),
        ("@huume, guest slipped", "guest slipped"),
        ("  @huume   help  ", "help"),
        ("no mention here", "no mention here"),
    ])
    def test_strips_leading_address(self, raw, expected):
        assert strip_mention(raw) == expected

    def test_only_strips_leading(self):
        # A mid-sentence mention is part of what the person said.
        assert strip_mention("tell @huume about it") == "tell @huume about it"


class TestLogIsTheDefault:
    @pytest.mark.parametrize("message", [
        "@huume the walk-in freezer is running at 48 degrees",
        "@huume Julia slipped in the back of house",
        "@huume I asked Jenna to bin the hot dogs and she rolled her eyes at me",
        "@huume guest threw his pizza on the ground after we refunded him",
        "@huume black mold in the corner of the stock room",
    ])
    def test_plain_reports_log(self, message):
        assert classify_intent(message) == LOG

    @pytest.mark.parametrize("message", [
        # Interrogative-looking REPORTS — the failure mode that loses an event.
        "@huume what a mess — the walk-in flooded overnight",
        "@huume here's what happened: the fryer tripped the breaker",
        "@huume what's broken: the ice machine, again",
        "@huume can't believe this, someone left the freezer open all night",
        "@huume who left the back door unlocked last night is beyond me",
        "@huume how the register drawer came up short today",
    ])
    def test_reports_that_look_like_questions_still_log(self, message):
        assert classify_intent(message) == LOG

    def test_no_question_mark_no_recall_phrase_logs(self):
        # "did" only leads an ASK via the anyone/we/you recall pattern or a
        # trailing "?" — a bare narrative starting with it is still a report.
        assert classify_intent("@huume did the delivery arrive short again today") == LOG

    @pytest.mark.parametrize("message", [
        # Reports mentioning "link" that must NOT be read as a link request.
        "@huume the link to the vendor portal is broken again",
        "@huume here's what happened, link's below: [photo]",
        "@huume sent the wrong link to a patient by mistake, need to fix it",
    ])
    def test_reports_mentioning_link_still_log(self, message):
        assert classify_intent(message) == LOG


class TestLink:
    @pytest.mark.parametrize("message", [
        "@huume send the reporting link",
        "@huume send the report link",
        "@huume can you share the anonymous link",
        "@huume drop the confidential link here",
        "@huume post the intake link",
        "@huume get the magic link",
        "@huume what's the link to the report",
        "@huume link to the report please",
    ])
    def test_link_requests(self, message):
        assert classify_intent(message) == LINK

    def test_help_wins_over_link(self):
        assert classify_intent("@huume what can you do with the reporting link") == HELP


class TestAsk:
    @pytest.mark.parametrize("message", [
        "@huume what happened at the store two weeks ago",
        "@huume what happened last week?",
        "@huume what's been logged in here lately",
        "@huume show me everything from this month",
        "@huume recap the last couple weeks",
        "@huume summarize what's on file here",
        "@huume catch me up",
        "@huume anything logged about the freezer?",
        "@huume did anyone report the ice machine yet",
        "@huume has anyone logged that already",
        "@huume remind me what we said about the patio door",
        "@huume list the safety stuff from July",
        "@huume can you show me the guest complaints",
        "@huume tell me about the incident by the pool deck",
    ])
    def test_recall_questions_ask(self, message):
        assert classify_intent(message) == ASK

    @pytest.mark.parametrize("message", [
        "@huume when did the freezer thing get reported?",
        "@huume is there anything on file about the fryer?",
        "@huume how many events are logged here?",
    ])
    def test_question_mark_plus_interrogative_lead_asks(self, message):
        assert classify_intent(message) == ASK


class TestOpsGroundingAsks:
    """Schedule/inventory questions (not requests) — added alongside
    `services/ems/channel_grounding.py` so these reach ASK instead of
    falling through to LOG or an unhelpful bare-interrogative answer."""

    @pytest.mark.parametrize("message", [
        "@huume who's working tomorrow?",
        "@huume who is scheduled for the morning shift",
        "@huume who's on shift right now",
        "@huume who's opening tomorrow",
        "@huume what's my schedule this week",
        "@huume when is my next shift",
        "@huume how much flour is left in stock",
        "@huume how many aprons do we have on hand",
    ])
    def test_ops_questions_ask(self, message):
        assert classify_intent(message) == ASK

    @pytest.mark.parametrize("message", [
        # Requests to BUILD/ASSIGN a shift must still win SCHEDULE — checked
        # before RECALL in classify_intent, unaffected by the new patterns.
        "@huume can you schedule two people for Saturday",
        "@huume I need an opener tomorrow at 8am",
    ])
    def test_schedule_build_requests_still_schedule(self, message):
        from app.matcha.services.ems.intent import SCHEDULE
        assert classify_intent(message) == SCHEDULE

    def test_staffing_report_still_logs(self):
        # A past-tense report, not a request or a question — bias-to-LOG.
        assert classify_intent(
            "@huume we needed more staff last night and someone got hurt"
        ) == LOG

    def test_stockout_report_is_still_inventory_not_ask(self):
        # Pre-existing INVENTORY fork (checked before RECALL) — regression
        # guard that the new "how much/many ... stock" ASK pattern didn't
        # steal this.
        from app.matcha.services.ems.intent import INVENTORY
        assert classify_intent("@huume we ran out of cups again") == INVENTORY


class TestHelp:
    @pytest.mark.parametrize("message", [
        "@huume help",
        "@huume what can you do",
        "@huume what can u do?",
        "@huume what do you do here",
        "@huume commands",
        "@huume how does this work",
        "@huume",  # bare poke
        "@huume ?",
    ])
    def test_capability_probes_help(self, message):
        assert classify_intent(message) == HELP

    def test_help_wins_over_ask(self):
        # "what can you do" matches an interrogative lead too — HELP is
        # checked first so a capability probe never burns a Gemini call.
        assert classify_intent("@huume what can you do?") == HELP


class TestGreetingPrefixedMention:
    """A greeting before the address ("Hey @huume ...") used to defeat every
    ^-anchored pattern below — the mention strip only worked at position 0.
    This is the exact "weekly recap logged as an event" failure class."""

    @pytest.mark.parametrize("message", [
        "Hey @huume give me a weekly recap",
        "hi @huume what happened last week",
        "ok @huume what happened yesterday",
        "please @huume recap the week",
        "good morning @huume catch me up",
    ])
    def test_greeting_prefixed_recall_asks(self, message):
        assert classify_intent(message) == ASK

    @pytest.mark.parametrize("message", [
        "good morning @huume the fridge died",
        "hey @huume the walk-in flooded overnight",
    ])
    def test_greeting_strip_does_not_flip_reports_to_ask(self, message):
        # A greeting must not make an ordinary report start matching
        # recall patterns it wouldn't otherwise match.
        assert classify_intent(message) == LOG

    def test_mid_sentence_mention_still_untouched(self):
        # Pinned alongside TestStripMention.test_only_strips_leading — the
        # greeting-prefix change must not affect a mention that isn't the
        # very first thing addressed.
        assert strip_mention("tell @huume about it") == "tell @huume about it"


class TestRecapPhrasingGaps:
    """Confirmed-misroute phrasings from the recap ticket — each used to
    fall to LOG (or, for the schedule case, get stolen by SCHEDULE) before
    the pattern additions."""

    @pytest.mark.parametrize("message", [
        "@huume can you give me a weekly recap of status updates",
        "@huume could you give me a recap",
        "@huume can I get a recap of the week",
        "@huume weekly recap of status updates",
        "@huume quick recap of the week please",
        "@huume whats been going on this week",
        "@huume what are the status updates",
        "@huume any status updates this week",
        "@huume I need a weekly recap of the schedule",
    ])
    def test_recap_phrasings_ask(self, message):
        assert classify_intent(message) == ASK

    def test_past_tense_report_stays_log(self):
        # LOG-bias guard — a bare past-tense report with no polite lead
        # must not be captured by the new recap/give/get patterns.
        assert classify_intent("@huume gave the patient the wrong form today") == LOG

    def test_schedule_still_wins_without_a_recap_noun(self):
        # The negative lookahead added to _SCHEDULE_PATTERNS only excludes
        # recap/summary wording — an ordinary staffing request must still
        # route to SCHEDULE, not get pulled into the new recall patterns.
        assert classify_intent("@huume we need an opener saturday") == "schedule"
