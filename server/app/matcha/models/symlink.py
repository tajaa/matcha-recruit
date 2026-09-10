"""Sym-link request/response models.

A sym-link is a bounded, guided task link: the sender picks a kind
(credential_upload / manager_review / info_update / custom), names a
recipient, and the public "tunnel chat" collects every required field +
attachment before landing on an editable review step. Completion stages a
submission the sender confirms — nothing is applied automatically.

Admin models are consumed by routes/symlink.py; the Public* models by
routes/intake/symlink_public.py. Public models are `extra="forbid"` and carry
the same size constants as the IR public chat so one body cap covers both.
"""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

SymlinkKind = Literal["credential_upload", "manager_review", "info_update", "custom"]
SymlinkStatus = Literal[
    "pending", "in_progress", "submitted", "applied", "rejected", "revoked", "expired",
]
SubmissionStatus = Literal["pending", "applied", "rejected"]

MAX_EXPIRY_DAYS = 30
DEFAULT_EXPIRY_DAYS = 14
MAX_PUBLIC_CHAT_BODY_BYTES = 64 * 1024
MAX_PUBLIC_CHAT_MESSAGE_CHARS = 600
MAX_CUSTOM_ITEMS = 12
MAX_ATTACHMENT_SLOTS = 6

# Unlock token travels in this header on every unlocked public call.
UNLOCK_HEADER = "X-Symlink-Unlock"


class SpecFieldOverride(BaseModel):
    """A sender-added checklist item (custom kind) or a tweak to a built-in field."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1, max_length=48, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=120)
    type: Literal["text", "long_text", "date_text", "number", "choice"] = "text"
    required: bool = True
    hint: Optional[str] = Field(None, max_length=300)
    choices: Optional[list[str]] = Field(None, max_length=12)

    @field_validator("choices")
    @classmethod
    def _clean_choices(cls, value):
        if value is None:
            return None
        cleaned = [c.strip()[:80] for c in value if isinstance(c, str) and c.strip()]
        return cleaned or None


# Every extension a recipient may upload, with the MIME the server stores it
# under (the client's content_type is never trusted). Mirrors
# routes/ir_incidents/_shared.py. A slot's `accept` list is a subset of this.
ATTACHMENT_EXT_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".csv": "text/csv",
}


class SpecAttachmentOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str = Field(..., min_length=1, max_length=48, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=120)
    required: bool = True
    # Extensions the slot accepts (e.g. [".pdf", ".docx"]). Omitted ⇒ a
    # sender-defined slot takes every supported type; a built-in slot keeps
    # its own default.
    accept: Optional[list[str]] = Field(None, max_length=len(ATTACHMENT_EXT_MIME))


class SpecOverrides(BaseModel):
    """What the sender may change on top of the kind's built-in spec."""

    model_config = ConfigDict(extra="forbid")

    goal: Optional[str] = Field(None, max_length=1000)
    fields: Optional[list[SpecFieldOverride]] = Field(None, max_length=MAX_CUSTOM_ITEMS)
    attachments: Optional[list[SpecAttachmentOverride]] = Field(None, max_length=MAX_ATTACHMENT_SLOTS)
    # credential_upload only — one of the portal's credential document types.
    document_type: Optional[str] = Field(None, max_length=40)


class SymlinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SymlinkKind
    title: str = Field(..., min_length=1, max_length=200)
    instructions: Optional[str] = Field(None, max_length=4000)
    recipient_name: str = Field(..., min_length=1, max_length=255)
    recipient_email: EmailStr
    employee_id: Optional[UUID] = None
    expires_in_days: int = Field(DEFAULT_EXPIRY_DAYS, ge=1, le=MAX_EXPIRY_DAYS)
    spec_overrides: SpecOverrides = Field(default_factory=SpecOverrides)
    send_email: bool = True


class SymlinkAttachmentOut(BaseModel):
    id: str
    slot: str
    file_name: str
    content_type: Optional[str] = None
    size_bytes: int
    uploaded_at: Optional[str] = None


class SymlinkSubmissionOut(BaseModel):
    id: str
    symlink_id: str
    status: SubmissionStatus
    fields: dict[str, Any]
    attachment_ids: list[str]
    submitted_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_note: Optional[str] = None
    applied_ref: Optional[dict[str, Any]] = None


class SymlinkOut(BaseModel):
    id: str
    kind: SymlinkKind
    title: str
    instructions: Optional[str] = None
    spec: dict[str, Any]
    recipient_name: str
    recipient_email: str
    employee_id: Optional[str] = None
    status: SymlinkStatus
    link: str
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    sent_at: Optional[str] = None
    last_sent_at: Optional[str] = None
    first_unlocked_at: Optional[str] = None
    completed_at: Optional[str] = None
    turn_count: int = 0
    email_sent: Optional[bool] = None


class SymlinkDetailOut(SymlinkOut):
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    known_fields: dict[str, Any] = Field(default_factory=dict)
    attachments: list[SymlinkAttachmentOut] = Field(default_factory=list)
    submission: Optional[SymlinkSubmissionOut] = None


class SubmissionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(None, max_length=2000)


class PasscodeOut(BaseModel):
    code: str
    rotated_at: Optional[str] = None
    next_rotation_at: Optional[str] = None
    rotation_weekday: int
    announce_channel_id: Optional[str] = None


class PasscodeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rotation_weekday: Optional[int] = Field(None, ge=0, le=6)
    # Explicit null clears the channel; omitted leaves it untouched.
    announce_channel_id: Optional[UUID] = None
    clear_announce_channel: bool = False


# ── Public (recipient) side ────────────────────────────────────────────────


class PublicUnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passcode: str = Field(..., min_length=1, max_length=32)
    # Honeypot — hidden field bots fill in. Silently "succeeds".
    internal_ref: Optional[str] = Field(None, max_length=200)


class PublicTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=MAX_PUBLIC_CHAT_MESSAGE_CHARS)


class PublicSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Final values from the review form. Coerced against the spec server-side.
    fields: dict[str, Any] = Field(default_factory=dict)
    internal_ref: Optional[str] = Field(None, max_length=200)


class PublicTurnResponse(BaseModel):
    assistant_message: str
    fields: dict[str, Any]
    complete: bool
    turn_count: int
    error: bool = False


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None
