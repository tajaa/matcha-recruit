"""Provider-contract tests for Huume's Responses adapter (no network)."""

from google.genai import types

from app.matcha.services.huume.luna_client import _messages


def test_messages_use_role_specific_text_types():
    payload = _messages([
        types.Content(role="user", parts=[types.Part(text="Build Wednesday")]),
        types.Content(role="model", parts=[types.Part(text="Which hours?")]),
        types.Content(role="user", parts=[types.Part(text="8am to 5pm")]),
    ])

    assert payload == [
        {"role": "user", "content": [{"type": "input_text", "text": "Build Wednesday"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "Which hours?"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "8am to 5pm"}]},
    ]
