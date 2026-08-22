"""Schedule-assistant voice transcription without real Gemini or DB calls."""

import asyncio
import io
import json
import wave
from types import SimpleNamespace
from uuid import uuid4

from app.matcha.routes.employee_schedule import assistant as assistant_route
from app.matcha.services.scheduling import schedule_voice


def _run(coro):
    return asyncio.run(coro)


class _FakeModels:
    def __init__(self, *, responses=None, raises=None):
        self.responses = list(responses or [])
        self.raises = raises
        self.calls = 0

    async def generate_content(self, *, model, contents, config):
        self.calls += 1
        if self.raises:
            raise self.raises
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    def __init__(self, models):
        self.aio = SimpleNamespace(models=models)


class _FakeResponse:
    def __init__(self, payload):
        self.text = payload if isinstance(payload, str) else json.dumps(payload)


def _wav_bytes(*, seconds=0.1, channels=1, sample_width=2, frame_rate=16_000):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(frame_rate)
        wav.writeframes(b"\x00" * int(seconds * frame_rate) * channels * sample_width)
    return out.getvalue()


class TestCoerceTranscript:
    def test_valid_transcript_is_trimmed(self):
        assert schedule_voice._coerce_transcript({"transcript": "  Add Dana Monday  "}) == "Add Dana Monday"

    def test_blank_or_invalid_payload_returns_none(self):
        assert schedule_voice._coerce_transcript({"transcript": "   "}) is None
        assert schedule_voice._coerce_transcript({"transcript": 12}) is None
        assert schedule_voice._coerce_transcript(["not", "an", "object"]) is None

    def test_transcript_is_clamped_to_chat_limit(self):
        transcript = schedule_voice._coerce_transcript({"transcript": "x" * 2_500})
        assert len(transcript) == schedule_voice.MAX_TRANSCRIPT_CHARS


class TestValidateScheduleWav:
    def test_accepts_client_pcm_format(self):
        schedule_voice.validate_schedule_wav(_wav_bytes())

    def test_rejects_wrong_pcm_shape(self):
        try:
            schedule_voice.validate_schedule_wav(_wav_bytes(channels=2))
        except ValueError as exc:
            assert "16 kHz mono PCM" in str(exc)
        else:
            raise AssertionError("stereo WAV should be rejected")

    def test_rejects_audio_over_duration_cap(self):
        try:
            schedule_voice.validate_schedule_wav(_wav_bytes(seconds=51))
        except ValueError as exc:
            assert "50 seconds or shorter" in str(exc)
        else:
            raise AssertionError("long WAV should be rejected")

    def test_rejects_truncated_frame_data(self):
        try:
            schedule_voice.validate_schedule_wav(_wav_bytes()[:-10])
        except ValueError as exc:
            assert "truncated or malformed" in str(exc)
        else:
            raise AssertionError("truncated WAV should be rejected")


class TestTranscribeScheduleRequest:
    def test_success_returns_verbatim_transcript(self, monkeypatch):
        models = _FakeModels(responses=[_FakeResponse({"transcript": "Sounds good."})])
        monkeypatch.setattr(schedule_voice, "genai_env_client", lambda: _FakeClient(models))

        result = _run(schedule_voice.transcribe_schedule_request(b"wav", "audio/wav"))

        assert result == {
            "available": True,
            "transcript": "Sounds good.",
            "model": schedule_voice.GEMINI_FLASH,
        }
        assert models.calls == 1

    def test_runtime_failure_never_raises_or_retries(self, monkeypatch):
        models = _FakeModels(raises=RuntimeError("boom"))
        monkeypatch.setattr(schedule_voice, "genai_env_client", lambda: _FakeClient(models))

        result = _run(schedule_voice.transcribe_schedule_request(b"wav", "audio/wav"))

        assert result["available"] is False
        assert result["transcript"] is None
        assert models.calls == 1

    def test_client_initialization_failure_never_raises(self, monkeypatch):
        def fail_client():
            raise RuntimeError("missing credentials")

        monkeypatch.setattr(schedule_voice, "genai_env_client", fail_client)

        result = _run(schedule_voice.transcribe_schedule_request(b"wav", "audio/wav"))

        assert result["available"] is False
        assert result["transcript"] is None

    def test_timeout_then_success_retries_once(self, monkeypatch):
        models = _FakeModels(responses=[
            asyncio.TimeoutError(),
            _FakeResponse({"transcript": "Add two openers"}),
        ])
        monkeypatch.setattr(schedule_voice, "genai_env_client", lambda: _FakeClient(models))

        result = _run(schedule_voice.transcribe_schedule_request(b"wav", "audio/wav"))

        assert result["available"] is True
        assert result["transcript"] == "Add two openers"
        assert models.calls == 2

    def test_invalid_json_then_success_retries_once(self, monkeypatch):
        models = _FakeModels(responses=[
            _FakeResponse("not json"),
            _FakeResponse({"transcript": "Cancel"}),
        ])
        monkeypatch.setattr(schedule_voice, "genai_env_client", lambda: _FakeClient(models))

        result = _run(schedule_voice.transcribe_schedule_request(b"wav", "audio/wav"))

        assert result["available"] is True
        assert result["transcript"] == "Cancel"
        assert models.calls == 2

    def test_valid_non_object_json_is_available_but_empty(self, monkeypatch):
        models = _FakeModels(responses=[_FakeResponse("[1, 2, 3]")])
        monkeypatch.setattr(schedule_voice, "genai_env_client", lambda: _FakeClient(models))

        result = _run(schedule_voice.transcribe_schedule_request(b"wav", "audio/wav"))

        assert result["available"] is True
        assert result["transcript"] is None


def test_voice_endpoint_classifies_command_and_applies_rate_limits(monkeypatch):
    company_id = uuid4()
    user_id = uuid4()
    rate_calls = []

    async def fake_require_company_id(current_user):
        return company_id

    async def fake_rate_limit(*args):
        rate_calls.append(args)

    async def fake_read_wav(file, max_bytes):
        assert max_bytes == schedule_voice.MAX_AUDIO_BYTES
        return b"wav"

    async def fake_transcribe(audio, mime_type):
        assert mime_type == "audio/wav"
        return {
            "available": True,
            "transcript": "Sounds good.",
            "model": "test-model",
        }

    monkeypatch.setattr(assistant_route, "require_company_id", fake_require_company_id)
    monkeypatch.setattr(assistant_route, "check_rate_limit", fake_rate_limit)
    monkeypatch.setattr(assistant_route, "read_wav_or_400", fake_read_wav)
    monkeypatch.setattr(assistant_route.schedule_voice, "validate_schedule_wav", lambda audio: None)
    monkeypatch.setattr(assistant_route.schedule_voice, "transcribe_schedule_request", fake_transcribe)

    result = _run(assistant_route.transcribe_schedule_voice(
        file=SimpleNamespace(content_type="audio/wav"),
        current_user=SimpleNamespace(id=user_id),
    ))

    assert result.transcript == "Sounds good."
    assert result.command == "confirm"
    assert rate_calls == [
        (f"user:{user_id}", "schedule_voice_parse_burst", 5, 60),
        (f"user:{user_id}", "schedule_voice_parse", 30, 3600),
        (str(company_id), "schedule_voice_parse_co", 120, 3600),
    ]
