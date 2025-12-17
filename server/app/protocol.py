import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


class MessageType:
    USER = "user"
    ASSISTANT = "assistant"
    STATUS = "status"
    SYSTEM = "system"
    COMMAND = "command"


class AudioMessageType:
    FROM_CLIENT = 0x01
    FROM_SERVER = 0x02


@dataclass
class SessionCommand:
    command: str  # "start_session", "stop_session", "send_text"
    interview_id: Optional[str] = None
    text: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "SessionCommand":
        return cls(
            command=data.get("command", ""),
            interview_id=data.get("interviewId"),
            text=data.get("text"),
        )


@dataclass
class ConversationMessage:
    type: str
    content: str
    timestamp: int

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def create(cls, msg_type: str, content: str) -> "ConversationMessage":
        return cls(
            type=msg_type,
            content=content,
            timestamp=int(time.time() * 1000),
        )


def parse_text_message(data: str) -> Optional[SessionCommand]:
    try:
        parsed = json.loads(data)
        if parsed.get("type") == MessageType.COMMAND:
            return SessionCommand.from_dict(parsed)
        if "command" in parsed:
            return SessionCommand.from_dict(parsed)
        return None
    except json.JSONDecodeError:
        return None


def frame_audio_for_client(pcm_data: bytes) -> bytes:
    """Frame audio data for sending to client."""
    return bytes([AudioMessageType.FROM_SERVER]) + pcm_data


def parse_audio_from_client(data: bytes) -> Optional[bytes]:
    """Parse audio data received from client."""
    if len(data) < 2:
        return None
    if data[0] == AudioMessageType.FROM_CLIENT:
        return data[1:]
    return None
