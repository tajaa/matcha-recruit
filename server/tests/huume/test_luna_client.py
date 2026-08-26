"""OpenAI Responses adapter regressions for Huume."""

from types import SimpleNamespace

import httpx
from google.genai import types

from app.matcha.services.huume.luna_client import _http_error_detail, _messages


def test_messages_use_responses_content_types_for_each_role():
    result = _messages([
        types.Content(role="user", parts=[types.Part(text="first prompt")]),
        types.Content(role="model", parts=[types.Part(text="first reply")]),
        types.Content(role="user", parts=[types.Part(text="second prompt")]),
    ])

    assert result == [
        {"role": "user", "content": [{"type": "input_text", "text": "first prompt"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "first reply"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "second prompt"}]},
    ]


def test_http_error_detail_preserves_provider_message_without_headers():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        400,
        request=request,
        json={"error": {"type": "invalid_request_error", "message": "Bad content type"}},
    )
    error = httpx.HTTPStatusError("400", request=request, response=response)

    assert _http_error_detail(error) == "invalid_request_error: Bad content type"


def test_messages_keep_empty_fallback_user_shaped():
    assert _messages([SimpleNamespace(role="model", parts=[])]) == [
        {"role": "user", "content": [{"type": "input_text", "text": "Hello."}]},
    ]


def test_messages_do_not_replay_assistant_images_as_user_input():
    result = _messages([
        types.Content(
            role="model",
            parts=[
                types.Part(text="Here is the image."),
                types.Part.from_bytes(data=b"not-a-real-image", mime_type="image/png"),
            ],
        ),
    ])

    assert result == [{
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Here is the image."}],
    }]
