"""Mood boards (`services/boards/`): what the dashboard and the Studio send and get."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cappe import CappeAsset
from ..services.boards.limits import (
    COORD_MAX,
    LINK_TITLE_MAX,
    MAX_PINS_PER_BOARD,
    NOTE_MAX,
    ROTATION_MAX,
    SIZE_MAX,
    SIZE_MIN,
    TITLE_MAX,
    URL_MAX,
    Z_MAX,
)

# Spelled out for the type checker; `test_cappe_boards.py` holds it to NOTE_COLORS.
NoteColor = Literal["yellow", "pink", "blue", "green", "purple", "white"]


def _whole(value: Optional[str]) -> Optional[str]:
    if value is not None and any(ord(c) == 0 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("Use whole Unicode characters")
    return value


class BoardTitle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=TITLE_MAX)

    @field_validator("title")
    @classmethod
    def named(cls, value: str) -> str:
        value = " ".join(_whole(value).split())
        if not value:
            raise ValueError("Name the board")
        return value


class Place(BaseModel):
    """Where a pin goes, in board units. Size is optional on create: the
    server picks one for the kind."""
    x: float = Field(ge=-COORD_MAX, le=COORD_MAX)
    y: float = Field(ge=-COORD_MAX, le=COORD_MAX)
    w: Optional[float] = Field(default=None, ge=SIZE_MIN, le=SIZE_MAX)
    h: Optional[float] = Field(default=None, ge=SIZE_MIN, le=SIZE_MAX)
    rotation: float = Field(default=0, ge=-ROTATION_MAX, le=ROTATION_MAX)


class PinCreate(Place):
    """A note, a link, or a picture already in the library. Files and
    screenshots go through the upload route."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["note", "link", "image"]
    note: Optional[str] = Field(default=None, max_length=NOTE_MAX)
    color: Optional[NoteColor] = None
    url: Optional[str] = Field(default=None, max_length=URL_MAX)
    asset_id: Optional[UUID] = None

    @field_validator("note", "url")
    @classmethod
    def whole(cls, value: Optional[str]) -> Optional[str]:
        return _whole(value)

    @model_validator(mode="after")
    def complete(self):
        if self.kind == "note" and not (self.note or "").strip():
            raise ValueError("Write something on the note")
        if self.kind == "link" and not (self.url or "").strip():
            raise ValueError("Paste a link")
        if self.kind == "image" and self.asset_id is None:
            raise ValueError("Pick a picture from the library, or upload one")
        return self


class PinPatch(BaseModel):
    """Move, size, turn, raise; a note's words and colour; a caption or label."""
    model_config = ConfigDict(extra="forbid")
    x: Optional[float] = Field(default=None, ge=-COORD_MAX, le=COORD_MAX)
    y: Optional[float] = Field(default=None, ge=-COORD_MAX, le=COORD_MAX)
    w: Optional[float] = Field(default=None, ge=SIZE_MIN, le=SIZE_MAX)
    h: Optional[float] = Field(default=None, ge=SIZE_MIN, le=SIZE_MAX)
    rotation: Optional[float] = Field(default=None, ge=-ROTATION_MAX, le=ROTATION_MAX)
    z: Optional[int] = Field(default=None, ge=0, le=Z_MAX)
    note: Optional[str] = Field(default=None, max_length=NOTE_MAX)
    color: Optional[NoteColor] = None
    title: Optional[str] = Field(default=None, max_length=LINK_TITLE_MAX)

    @field_validator("note", "title")
    @classmethod
    def whole(cls, value: Optional[str]) -> Optional[str]:
        return _whole(value)


class LayoutItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    x: float = Field(ge=-COORD_MAX, le=COORD_MAX)
    y: float = Field(ge=-COORD_MAX, le=COORD_MAX)
    w: float = Field(ge=SIZE_MIN, le=SIZE_MAX)
    h: float = Field(ge=SIZE_MIN, le=SIZE_MAX)
    rotation: float = Field(default=0, ge=-ROTATION_MAX, le=ROTATION_MAX)
    z: int = Field(ge=0, le=Z_MAX)


class Layout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pins: list[LayoutItem] = Field(max_length=MAX_PINS_PER_BOARD)


class PinToLibrary(BaseModel):
    """Add a pinned picture to the site's library so a story can use it."""
    model_config = ConfigDict(extra="forbid")
    rights_attested: bool
    ai_made: bool = False
    alt: Optional[str] = Field(default=None, max_length=500)
    credit_line: Optional[str] = Field(default=None, max_length=500)


class BoardOut(BaseModel):
    id: UUID
    title: str
    pin_count: int = 0
    covers: list[str] = []
    created_at: datetime
    updated_at: datetime


class BoardList(BaseModel):
    boards: list[BoardOut]


class PinOut(BaseModel):
    id: UUID
    board_id: UUID
    kind: Literal["image", "file", "note", "link"]
    x: float
    y: float
    w: float
    h: float
    rotation: float
    z: int
    asset_id: Optional[UUID] = None
    in_library: bool = False
    src: Optional[str] = None
    full: Optional[str] = None
    file_url: Optional[str] = None
    alt: Optional[str] = None
    filename: Optional[str] = None
    mime: Optional[str] = None
    size_bytes: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    note: Optional[str] = None
    color: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    site_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BoardDetail(BaseModel):
    board: BoardOut
    pins: list[PinOut]
    # The library pictures among the pins, whole (the Studio places them).
    assets: list[CappeAsset] = []


class LayoutResult(BaseModel):
    moved: int
