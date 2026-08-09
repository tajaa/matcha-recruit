"""Pydantic shapes — flyer design assistant (see services/flyer_ai/)."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

_KNOWN_KINDS = frozenset({"text", "image", "sticker", "shape", "qr"})


class FlyerAiSelection(BaseModel):
    """What the person has selected in the editor right now, so "this" and
    "here" resolve to something instead of being guessed at.

    Deliberately lenient, same as Cappe's `CappeMerlinSelection`: a stale or
    malformed selection must never fail the turn. Editor state can move between
    the click and this request landing, and losing the whole prompt over that is
    a far worse outcome than answering about the wrong layer.
    """
    layer: str = Field(max_length=100)
    kind: Optional[str] = Field(default=None, max_length=20)
    text: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="before")
    @classmethod
    def _degrade(cls, data: Any) -> Any:
        """Sanitize BEFORE field validation, so an out-of-contract value
        degrades instead of 422ing a request the person can no longer resend."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if out.get("kind") not in _KNOWN_KINDS:
            out["kind"] = None
        text = out.get("text")
        if isinstance(text, str) and len(text) > 300:
            out["text"] = text[:300]
        return out


class FlyerAiHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)
    # Compact recap of what an assistant turn changed ("Moved claim QR; Edited
    # headline"), sent instead of raw ops to keep the transcript cheap.
    ops_summary: Optional[str] = Field(default=None, max_length=2000)


class FlyerAssistRequest(BaseModel):
    """The client is the source of truth for the document: the assistant never
    reads or writes `design_json`. The design comes in, the revised design goes
    back, and the editor's existing autosave is what persists it."""
    message: str = Field(min_length=1, max_length=1000)
    # Byte-capped in the route, not here — an item count doesn't bound a
    # document, and the cap has to match the one the save path enforces.
    design: dict[str, Any]
    history: list[FlyerAiHistoryTurn] = Field(default_factory=list, max_length=20)
    selection: Optional[FlyerAiSelection] = None


class FlyerOpResult(BaseModel):
    ok: bool
    summary: str


class FlyerAiRejection(BaseModel):
    op: dict[str, Any]
    reason: str


class FlyerAssistResponse(BaseModel):
    message: str
    # The document AFTER the ops were applied server-side. Clients adopt this
    # wholesale rather than folding ops themselves — see services/flyer_ai/apply.py.
    design: dict[str, Any]
    ops: list[dict[str, Any]] = Field(default_factory=list)
    results: list[FlyerOpResult] = Field(default_factory=list)
    rejected: list[FlyerAiRejection] = Field(default_factory=list)


class FlyerIdea(BaseModel):
    key: str
    label: str
    blurb: str
    design: dict[str, Any]


class FlyerIdeasResponse(BaseModel):
    ideas: list[FlyerIdea]


class FlyerAiSchemaResponse(BaseModel):
    """The server's vocabulary, so a client picker can't drift from what the
    validators accept. Same role as Cappe's `GET /merlin/schema`."""
    palette_tokens: list[str]
    palettes: list[dict[str, Any]]
    layouts: list[dict[str, Any]]
    fonts: list[str]
    layer_kinds: list[str]
    addable_layer_kinds: list[str]
    ops: list[str]
    max_ops_per_turn: int


__all__ = [
    "FlyerAiSelection",
    "FlyerAiHistoryTurn",
    "FlyerAssistRequest",
    "FlyerOpResult",
    "FlyerAiRejection",
    "FlyerAssistResponse",
    "FlyerIdea",
    "FlyerIdeasResponse",
    "FlyerAiSchemaResponse",
]
