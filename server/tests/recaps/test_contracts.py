from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.matcha.models.matcha_work.recaps import Asset, Event, Fact, Manifest, Preferences, Scene, Statuses, clip
from app.matcha.services.matcha_work.recaps import adapters, storyboard

NOW = datetime.now(timezone.utc)


def event(**over):
    return Event(title="Verified result", occurred_at=NOW, kind="phase_completed", **over)


@pytest.mark.parametrize("over", [
    {"title": "x" * 161}, {"outcome": "success"}, {"occurred_at": datetime.now()},
    {"facts": [{"label": "x", "value": "x" * 301}]}, {"raw_body": "private"},
    {"facts": [{"label": "x", "value": "ok"}] * 7},
])
def test_events_reject_unknown_unbounded_and_naive_input(over):
    with pytest.raises(ValidationError):
        Event.model_validate({"title": "ok", "occurred_at": NOW, "kind": "result", **over})


@pytest.mark.parametrize("value", [1, "false", None, []])
def test_preferences_require_explicit_booleans(value):
    with pytest.raises(ValidationError):
        Preferences(enabled=value, email_enabled=False)


def test_utf8_grapheme_display_and_manifest_round_trip():
    assert clip("é" * 10, 4) == "ééé…"
    assert not clip("ab\u0301cd", 3).endswith("\u0301…")
    assert len(clip("🤖" * 200, 160)) <= 160
    assert clip(" hi\n there ", 20) == "hi there"
    original = Manifest(scenes=[Scene(event=event(facts=[Fact(label="家", value="🏡")]), seconds=4)])
    assert Manifest.model_validate_json(original.model_dump_json()).digest() == original.digest()
    changed = original.model_copy(deep=True)
    changed.scenes[0].event.title = "Different"
    assert changed.digest() != original.digest()


def test_manifest_rejects_over_duration_and_scene_count():
    for scenes in ([Scene(event=event(), seconds=20)] * 7, [Scene(event=event(), seconds=2)] * 13, []):
        with pytest.raises(ValidationError):
            Manifest(scenes=scenes)
    with pytest.raises(ValidationError):
        Statuses(ids=[uuid4() for _ in range(51)])


@pytest.mark.parametrize("key", ["https://cdn.example.com/video.mp4", "../../etc/passwd", "espresso-recaps/../../secret", "s3://private/video"])
def test_asset_keys_are_generated_private_references(key):
    with pytest.raises(ValidationError):
        Asset(key=key, sha256="a" * 64, bytes=1, mime="video/mp4")


def test_storyboard_caps_runtime_preserves_final_and_every_warning_type():
    events = [{"snapshot": Event(kind="request" if i == 0 else "result" if i == 127 else "phase_completed",
               title=f"Stage {i}", occurred_at=NOW).model_dump(mode="json")} for i in range(128)]
    for i, outcome in enumerate(sorted(storyboard.CONSEQUENTIAL), 1):
        events[i]["snapshot"]["outcome"] = outcome
    result = storyboard.build(events)
    assert len(result.scenes) <= 12 and sum(s.seconds for s in result.scenes) <= 120
    assert result.scenes[-1].event.title == "Stage 127"
    warnings = next(s.event for s in result.scenes if s.event.kind == "warning")
    assert {fact.label for fact in warnings.facts} == storyboard.CONSEQUENTIAL
    assert storyboard.build(events).digest() == result.digest()
    assert sum(s.seconds for s in storyboard.build(events[:1]).scenes) == 4
    with pytest.raises(ValueError, match="no evidence"):
        storyboard.build([])


@pytest.mark.parametrize("status,kind,result,expected", [
    ("ok", "commit", {"mode": "live"}, "confirmed"),
    ("ok", "commit", {"mode": "dry_run"}, "dry_run"),
    ("ok", "commit", {}, "dry_run"),
    ("unknown", "commit", {"mode": "live"}, "unknown"),
    ("claimed", "commit", {"mode": "live"}, "unknown"),
    ("error", "commit", {"mode": "live"}, "failed"),
    ("denied", "policy", {}, "failed"), ("held", "policy", {}, "held"),
    ("ok", "draft", {}, "drafted"), ("ok", "read", {}, "observed"),
])
def test_action_adapter_never_infers_success_from_ok(status, kind, result, expected):
    step = {"tool": "send_email", "status": status, "kind": kind, "result": result,
            "created_at": NOW, "args": {"bcc": "private@example.com", "body": "secret"}, "label": "secret"}
    snapshot = adapters.step_event(step)
    assert snapshot.outcome == expected
    assert "secret" not in snapshot.model_dump_json() and "bcc" not in snapshot.model_dump_json()
    unknown = adapters.step_event({**step, "tool": "unknown_tool"})
    if kind in adapters.ACTING:
        # An action with no title of its own is still kept, with none of its payload.
        assert unknown.outcome == expected and "secret" not in unknown.model_dump_json()
    else:
        assert unknown is None


@pytest.mark.parametrize("tool", ["buy_item", "book_reservation", "register_domain", "a_future_commit_tool"])
def test_uncertain_or_failed_actions_outside_the_title_list_are_kept(tool):
    for status, expected in (("unknown", "unknown"), ("claimed", "unknown"), ("error", "failed")):
        event = adapters.step_event({"tool": tool, "kind": "commit", "status": status,
                                     "result": {"mode": "live"}, "created_at": NOW})
        assert event.outcome == expected and event.outcome in storyboard.CONSEQUENTIAL


@pytest.mark.parametrize("tool,kind", [("fetch_page", "fetch"), ("web_search", "search"),
                                       ("view_page", "browse"), ("read_email", "read")])
def test_a_read_that_failed_is_not_a_warning(tool, kind):
    for status in ("error", "skipped"):
        assert adapters.step_event({"tool": tool, "kind": kind, "status": status, "result": {},
                                    "created_at": NOW}) is None
    assert adapters.step_event({"tool": tool, "kind": kind, "status": "ok", "result": {},
                                "created_at": NOW}).outcome == "observed"


def test_bulk_email_count_is_allowlisted_without_recipients():
    step = {"tool": "archive_email", "kind": "commit", "status": "ok", "created_at": NOW,
            "result": {"mode": "live", "weight": 12, "body": "private"}}
    assert adapters.step_event(step).facts[-1].value == "12"
