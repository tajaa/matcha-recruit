"""Registry-driven channel grounding beyond ems_events — proves the policy
(admin gate, feature-off skip, one-topic-failure isolation) without a real
database. See services/ems/channel_grounding.py's module docstring for why
the topic list is deliberately short.

    cd server && ./venv/bin/python -m pytest tests/ems/test_channel_grounding.py -q
"""

import asyncio

import pytest

from app.matcha.services.ems import channel_grounding


def _run(coro):
    return asyncio.run(coro)


class TestFetchTopicBlocks:
    def test_admin_only_topics_are_never_queried_for_an_employee(self, monkeypatch):
        called_topics = []

        async def fake_impl(conn, *, company_id, topic, features=None, query=None, days=None, location_id=None):
            called_topics.append(topic)
            return {"topic": topic, "upcoming_shifts": []}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill._lookup_context_impl", fake_impl,
        )
        _run(channel_grounding.fetch_topic_blocks(
            None, company_id="c1", features={t.topic: True for t in channel_grounding.CHANNEL_TOPICS},
            is_admin=False, location_id=None,
        ))
        admin_only_topics = {t.topic for t in channel_grounding.CHANNEL_TOPICS if t.admin_only}
        assert not (set(called_topics) & admin_only_topics)
        non_admin_topics = {t.topic for t in channel_grounding.CHANNEL_TOPICS if not t.admin_only}
        assert set(called_topics) == non_admin_topics

    def test_admin_asker_reaches_every_topic(self, monkeypatch):
        called_topics = []

        async def fake_impl(conn, *, company_id, topic, features=None, query=None, days=None, location_id=None):
            called_topics.append(topic)
            return {"topic": topic, "module": "off"}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill._lookup_context_impl", fake_impl,
        )
        _run(channel_grounding.fetch_topic_blocks(
            None, company_id="c1", features={}, is_admin=True, location_id=None,
        ))
        assert set(called_topics) == {t.topic for t in channel_grounding.CHANNEL_TOPICS}

    def test_module_off_result_produces_no_block(self, monkeypatch):
        async def fake_impl(conn, *, company_id, topic, features=None, query=None, days=None, location_id=None):
            return {"topic": topic, "module": "off"}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill._lookup_context_impl", fake_impl,
        )
        blocks = _run(channel_grounding.fetch_topic_blocks(
            None, company_id="c1", features={}, is_admin=True, location_id=None,
        ))
        assert blocks == []

    def test_empty_render_produces_no_block(self, monkeypatch):
        # module is "on" (no {"module": "off"}) but the render fn finds
        # nothing to say — still must not add an empty section.
        async def fake_impl(conn, *, company_id, topic, features=None, query=None, days=None, location_id=None):
            return {"topic": topic}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill._lookup_context_impl", fake_impl,
        )
        blocks = _run(channel_grounding.fetch_topic_blocks(
            None, company_id="c1", features={}, is_admin=True, location_id=None,
        ))
        assert blocks == []

    def test_one_topic_raising_does_not_kill_the_others(self, monkeypatch):
        async def fake_impl(conn, *, company_id, topic, features=None, query=None, days=None, location_id=None):
            if topic == "schedule":
                raise RuntimeError("boom")
            if topic == "inventory":
                return {"topic": topic, "items": [{"id": "i1", "name": "Flour", "current_quantity": 3, "unit": "bags"}]}
            return {"topic": topic, "module": "off"}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill._lookup_context_impl", fake_impl,
        )
        blocks = _run(channel_grounding.fetch_topic_blocks(
            None, company_id="c1", features={}, is_admin=True, location_id=None,
        ))
        assert len(blocks) == 1
        assert blocks[0][0] == "INVENTORY ON HAND"
        assert "Flour" in blocks[0][1]

    def test_location_scoped_topics_pass_location_id_through(self, monkeypatch):
        seen = {}

        async def fake_impl(conn, *, company_id, topic, features=None, query=None, days=None, location_id=None):
            seen[topic] = location_id
            return {"topic": topic, "module": "off"}

        monkeypatch.setattr(
            "app.matcha.services.huume.onboarding_skill._lookup_context_impl", fake_impl,
        )
        _run(channel_grounding.fetch_topic_blocks(
            None, company_id="c1", features={}, is_admin=True, location_id="loc-1",
        ))
        for t in channel_grounding.CHANNEL_TOPICS:
            expected = "loc-1" if t.location_scoped else None
            assert seen[t.topic] == expected


class TestHelpLines:
    def test_admin_only_lines_excluded_for_employee(self):
        from app.matcha.services.huume.onboarding_skill import _TOPIC_REQUIRED_FEATURE
        features = {flag: True for flag in _TOPIC_REQUIRED_FEATURE.values()}
        lines = channel_grounding.help_lines(features=features, is_admin=False)
        admin_only_bullets = [t.help_line for t in channel_grounding.CHANNEL_TOPICS if t.admin_only]
        assert not any(bullet in "\n".join(lines) for bullet in admin_only_bullets)

    def test_feature_off_excludes_line_even_for_admin(self):
        lines = channel_grounding.help_lines(features={}, is_admin=True)
        assert lines == []

    def test_admin_with_everything_on_sees_every_line(self):
        from app.matcha.services.huume.onboarding_skill import _TOPIC_REQUIRED_FEATURE
        features = {flag: True for flag in _TOPIC_REQUIRED_FEATURE.values()}
        lines = channel_grounding.help_lines(features=features, is_admin=True)
        assert len(lines) == len(channel_grounding.CHANNEL_TOPICS)


class TestRenderFunctions:
    def test_render_schedule_empty(self):
        assert channel_grounding._render_schedule({"upcoming_shifts": []}) == ""

    def test_render_schedule_with_shift(self):
        import datetime
        result = {"upcoming_shifts": [{
            "starts_at": datetime.datetime(2026, 8, 3, 8, 0, tzinfo=datetime.timezone.utc),
            "ends_at": datetime.datetime(2026, 8, 3, 16, 0, tzinfo=datetime.timezone.utc),
            "role": "Opener", "assignees": ["Aisha Rivera"], "assigned_count": 1, "required_staff": 1,
        }]}
        text = channel_grounding._render_schedule(result)
        assert "Aisha Rivera" in text
        assert "Opener" in text

    def test_render_inventory_empty(self):
        assert channel_grounding._render_inventory({"items": []}) == ""

    def test_render_incidents_empty(self):
        assert channel_grounding._render_incidents({"incidents": []}) == ""

    def test_render_training_empty(self):
        assert channel_grounding._render_training({"overdue": []}) == ""

    def test_render_credentials_empty(self):
        assert channel_grounding._render_credentials({"expiring_or_overdue": []}) == ""

    def test_render_pto_empty(self):
        assert channel_grounding._render_pto({"active_leave": [], "upcoming_pto": []}) == ""
