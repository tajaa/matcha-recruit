"""Regression tests for `_row_metadata`/`_system_message_payload` — asyncpg
returns JSONB as a raw str (no set_type_codec('jsonb', …) registered on the
pool), and the WS broadcast payload builder used to hand that string
straight to the client. `msg.metadata?.action` on a string is `undefined`,
so a live Huume event-draft (or any other) pill never rendered its
Confirm/Reject card until the channel was reloaded and the REST snapshot
(which does decode, see routes/channels.py:155) replaced it.

    cd server && ./venv/bin/python -m pytest tests/channels_ws/test_system_message_payload.py -q
"""

from datetime import datetime, timezone

from app.werk.routes import channels_ws


def _sys_row(metadata):
    return {
        "id": "msg-1",
        "channel_id": "chan-1",
        "content": "Add it to Events? Reply confirm or not an event.",
        "message_type": "system",
        "metadata": metadata,
        "created_at": datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc),
    }


class TestRowMetadata:
    def test_decodes_json_string(self):
        assert channels_ws._row_metadata(
            _sys_row('{"action": {"kind": "event_draft"}}')
        ) == {"action": {"kind": "event_draft"}}

    def test_passes_through_dict_unchanged(self):
        metadata = {"action": {"kind": "event_draft"}}
        assert channels_ws._row_metadata(_sys_row(metadata)) == metadata

    def test_none_becomes_empty_dict(self):
        assert channels_ws._row_metadata(_sys_row(None)) == {}

    def test_garbage_string_becomes_empty_dict_without_raising(self):
        assert channels_ws._row_metadata(_sys_row("not json")) == {}

    def test_valid_json_wrong_shape_becomes_empty_dict(self):
        assert channels_ws._row_metadata(_sys_row('"a string"')) == {}
        assert channels_ws._row_metadata(_sys_row("[1, 2]")) == {}


class TestSystemMessagePayload:
    def test_regression_string_metadata_survives_to_action(self):
        """The exact read MessageList.tsx:118 performs
        (`msg.metadata?.action`) must succeed against the broadcast payload,
        not just against a REST-fetched row."""
        row = _sys_row('{"action": {"kind": "event_draft", "id": "draft-1", "status": "pending"}}')
        payload = channels_ws._system_message_payload("chan-1", row)
        assert payload["metadata"]["action"] == {
            "kind": "event_draft", "id": "draft-1", "status": "pending",
        }

    def test_dict_metadata_still_works(self):
        row = _sys_row({"action": {"kind": "event_draft", "id": "draft-1", "status": "pending"}})
        payload = channels_ws._system_message_payload("chan-1", row)
        assert payload["metadata"]["action"]["kind"] == "event_draft"
