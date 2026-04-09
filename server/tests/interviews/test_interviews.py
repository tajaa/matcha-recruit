"""Tests for the interview system: models, audio protocol, prompt selection, transcript formatting."""

import sys
from types import ModuleType

# Stub google.genai before importing app code
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
types_module.LiveConnectConfig = lambda **kw: None
types_module.SpeechConfig = lambda **kw: None
types_module.VoiceConfig = lambda **kw: None
types_module.PrebuiltVoiceConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

import pytest
from pydantic import ValidationError
from typing import get_args

from app.matcha.models.interview import (
    InterviewType,
    TutorSessionCreate,
    InterviewStart,
    InterviewCreate,
)
from app.protocol import (
    MessageType,
    AudioMessageType,
    frame_audio_for_client,
    parse_audio_from_client,
    ConversationMessage,
    SessionCommand,
    parse_text_message,
)
from app.core.services.gemini_session import (
    InterviewType as GeminiInterviewType,
    GeminiLiveSession,
    TUTOR_LANGUAGE_ENGLISH_PROMPT,
    TUTOR_LANGUAGE_SPANISH_PROMPT,
    TUTOR_INTERVIEW_PREP_PROMPT,
    INTERVIEW_ROLE_GUIDANCE,
)


# ---------------------------------------------------------------------------
# 1. InterviewType literal values
# ---------------------------------------------------------------------------

class TestInterviewType:
    def test_model_interview_types(self):
        expected = {"culture", "candidate", "screening", "tutor_interview", "tutor_language", "investigation"}
        assert set(get_args(InterviewType)) == expected

    def test_gemini_interview_types_superset(self):
        """Gemini session supports all model types plus phone_call."""
        expected = {"culture", "candidate", "screening", "tutor_interview", "tutor_language", "investigation", "phone_call"}
        assert set(get_args(GeminiInterviewType)) == expected


# ---------------------------------------------------------------------------
# 2. TutorSessionCreate model validation
# ---------------------------------------------------------------------------

class TestTutorSessionCreate:
    def test_valid_interview_prep(self):
        m = TutorSessionCreate(mode="interview_prep", interview_role="CTO")
        assert m.mode == "interview_prep"
        assert m.interview_role == "CTO"

    def test_valid_language_test(self):
        m = TutorSessionCreate(mode="language_test", language="es")
        assert m.mode == "language_test"
        assert m.language == "es"

    def test_valid_duration_values(self):
        for d in (2, 5, 8):
            m = TutorSessionCreate(mode="interview_prep", duration_minutes=d)
            assert m.duration_minutes == d

    def test_invalid_duration_rejected(self):
        with pytest.raises(ValidationError):
            TutorSessionCreate(mode="interview_prep", duration_minutes=10)

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            TutorSessionCreate(mode="invalid_mode")

    def test_invalid_language_rejected(self):
        with pytest.raises(ValidationError):
            TutorSessionCreate(mode="language_test", language="fr")

    def test_company_modes_accepted(self):
        for mode in ("culture", "candidate", "screening"):
            m = TutorSessionCreate(mode=mode)
            assert m.mode == mode

    def test_defaults(self):
        m = TutorSessionCreate(mode="interview_prep")
        assert m.language is None
        assert m.duration_minutes is None
        assert m.company_id is None
        assert m.interview_role is None
        assert m.is_practice is False


# ---------------------------------------------------------------------------
# 3. Audio protocol
# ---------------------------------------------------------------------------

class TestAudioProtocol:
    def test_frame_audio_prepends_0x02(self):
        pcm = b"\x00\x01\x02\x03"
        framed = frame_audio_for_client(pcm)
        assert framed[0] == 0x02
        assert framed[1:] == pcm

    def test_parse_audio_strips_0x01(self):
        raw = bytes([0x01]) + b"\xAA\xBB\xCC"
        parsed = parse_audio_from_client(raw)
        assert parsed == b"\xAA\xBB\xCC"

    def test_parse_audio_wrong_prefix_returns_none(self):
        raw = bytes([0x02]) + b"\xAA\xBB"
        assert parse_audio_from_client(raw) is None

    def test_parse_audio_too_short_returns_none(self):
        assert parse_audio_from_client(b"\x01") is None
        assert parse_audio_from_client(b"") is None

    def test_frame_then_parse_roundtrip_fails(self):
        """frame uses 0x02, parse expects 0x01 -- they are different directions."""
        pcm = b"\x10\x20\x30"
        framed = frame_audio_for_client(pcm)
        assert parse_audio_from_client(framed) is None

    def test_empty_audio_framing(self):
        framed = frame_audio_for_client(b"")
        assert framed == bytes([0x02])


# ---------------------------------------------------------------------------
# 4. MessageType constants
# ---------------------------------------------------------------------------

class TestMessageType:
    def test_user(self):
        assert MessageType.USER == "user"

    def test_assistant(self):
        assert MessageType.ASSISTANT == "assistant"

    def test_status(self):
        assert MessageType.STATUS == "status"

    def test_system(self):
        assert MessageType.SYSTEM == "system"

    def test_command(self):
        assert MessageType.COMMAND == "command"

    def test_audio_from_client(self):
        assert AudioMessageType.FROM_CLIENT == 0x01

    def test_audio_from_server(self):
        assert AudioMessageType.FROM_SERVER == 0x02


# ---------------------------------------------------------------------------
# 5. Prompt selection logic
# ---------------------------------------------------------------------------

class TestPromptSelection:
    def test_tutor_language_en_gets_english_prompt(self):
        """When tutor_language with 'en', should select the English prompt."""
        # The connect() method: if tutor_language == "es" -> Spanish, else -> English
        assert "English language conversation partner" in TUTOR_LANGUAGE_ENGLISH_PROMPT
        assert "español" not in TUTOR_LANGUAGE_ENGLISH_PROMPT

    def test_tutor_language_es_gets_spanish_prompt(self):
        assert "español" in TUTOR_LANGUAGE_SPANISH_PROMPT
        assert "English language conversation partner" not in TUTOR_LANGUAGE_SPANISH_PROMPT

    def test_tutor_interview_prompt_has_role_placeholder(self):
        assert "{interview_role}" in TUTOR_INTERVIEW_PREP_PROMPT
        assert "{role_guidance}" in TUTOR_INTERVIEW_PREP_PROMPT
        assert "{feedback_focus}" in TUTOR_INTERVIEW_PREP_PROMPT

    def test_role_guidance_has_default(self):
        assert "default" in INTERVIEW_ROLE_GUIDANCE

    def test_role_guidance_known_roles(self):
        for role in ("VP of People", "CTO", "Head of Marketing", "Junior Engineer"):
            assert role in INTERVIEW_ROLE_GUIDANCE
            assert "QUESTIONS TO ASK" in INTERVIEW_ROLE_GUIDANCE[role]

    def test_role_guidance_has_feedback_focus(self):
        for key, guidance in INTERVIEW_ROLE_GUIDANCE.items():
            assert "FEEDBACK_FOCUS:" in guidance, f"Missing FEEDBACK_FOCUS in role: {key}"


# ---------------------------------------------------------------------------
# 6. Transcript formatting — speaker labels by interview type
# ---------------------------------------------------------------------------

class TestTranscriptFormatting:
    """Test GeminiLiveSession.get_transcript_text() speaker labels."""

    def _make_session(self, interview_type: str) -> GeminiLiveSession:
        """Create a session without connecting to Gemini."""
        # Bypass __init__ to avoid needing a real client
        session = object.__new__(GeminiLiveSession)
        session._input_transcript_buffer = ""
        session._output_transcript_buffer = ""
        session.session_transcript = []
        session._interview_type = interview_type
        return session

    def _add_exchange(self, session, user_text="Hello", assistant_text="Hi there"):
        session.session_transcript.append(("user", user_text))
        session.session_transcript.append(("assistant", assistant_text))

    def test_culture_labels(self):
        s = self._make_session("culture")
        self._add_exchange(s)
        text = s.get_transcript_text()
        assert "HR: Hello" in text
        assert "Interviewer: Hi there" in text

    def test_candidate_labels(self):
        s = self._make_session("candidate")
        self._add_exchange(s)
        text = s.get_transcript_text()
        assert "Candidate: Hello" in text
        assert "Interviewer: Hi there" in text

    def test_screening_labels(self):
        s = self._make_session("screening")
        self._add_exchange(s)
        text = s.get_transcript_text()
        assert "Candidate: Hello" in text
        assert "Interviewer: Hi there" in text

    def test_tutor_interview_labels(self):
        s = self._make_session("tutor_interview")
        self._add_exchange(s)
        text = s.get_transcript_text()
        assert "Learner: Hello" in text
        assert "Coach: Hi there" in text

    def test_tutor_language_labels(self):
        s = self._make_session("tutor_language")
        self._add_exchange(s)
        text = s.get_transcript_text()
        assert "Learner: Hello" in text
        assert "Tutor: Hi there" in text

    def test_investigation_labels(self):
        s = self._make_session("investigation")
        self._add_exchange(s)
        text = s.get_transcript_text()
        assert "Interviewee: Hello" in text
        assert "Investigator: Hi there" in text

    def test_phone_call_labels(self):
        s = self._make_session("phone_call")
        self._add_exchange(s)
        text = s.get_transcript_text()
        assert "Leasing Office: Hello" in text
        assert "Agent: Hi there" in text

    def test_flushes_remaining_buffers(self):
        s = self._make_session("culture")
        s._input_transcript_buffer = "leftover user text"
        s._output_transcript_buffer = "leftover assistant text"
        text = s.get_transcript_text()
        assert "HR: leftover user text" in text
        assert "Interviewer: leftover assistant text" in text

    def test_empty_transcript(self):
        s = self._make_session("culture")
        assert s.get_transcript_text() == ""

    def test_multiple_turns(self):
        s = self._make_session("tutor_interview")
        s.session_transcript = [
            ("user", "First question answer"),
            ("assistant", "Feedback on first"),
            ("user", "Second answer"),
            ("assistant", "Feedback on second"),
        ]
        text = s.get_transcript_text()
        lines = text.split("\n\n")
        assert len(lines) == 4
        assert lines[0] == "Learner: First question answer"
        assert lines[1] == "Coach: Feedback on first"


# ---------------------------------------------------------------------------
# 7. Protocol helper models
# ---------------------------------------------------------------------------

class TestProtocolHelpers:
    def test_conversation_message_create(self):
        msg = ConversationMessage.create(MessageType.USER, "test")
        assert msg.type == "user"
        assert msg.content == "test"
        assert isinstance(msg.timestamp, int)

    def test_conversation_message_to_json(self):
        msg = ConversationMessage.create(MessageType.ASSISTANT, "hello")
        import json
        data = json.loads(msg.to_json())
        assert data["type"] == "assistant"
        assert data["content"] == "hello"

    def test_session_command_from_dict(self):
        cmd = SessionCommand.from_dict({"command": "start_session", "interviewId": "abc"})
        assert cmd.command == "start_session"
        assert cmd.interview_id == "abc"

    def test_parse_text_message_command(self):
        import json
        msg = json.dumps({"type": "command", "command": "stop_session"})
        cmd = parse_text_message(msg)
        assert cmd is not None
        assert cmd.command == "stop_session"

    def test_parse_text_message_invalid_json(self):
        assert parse_text_message("not json") is None

    def test_parse_text_message_no_command(self):
        import json
        assert parse_text_message(json.dumps({"type": "user", "content": "hi"})) is None
