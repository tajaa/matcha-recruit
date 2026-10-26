"""Private reader annotations; offsets are UTF-16, as in browser Ranges."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReaderQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exact: str = Field(min_length=1, max_length=2000)
    prefix: str = Field(default="", max_length=64)
    suffix: str = Field(default="", max_length=64)
    start: int = Field(ge=0, le=10_000_000)

    @field_validator("exact", "prefix", "suffix")
    @classmethod
    def printable(cls, value: str) -> str:
        if any(ord(c) == 0 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Use whole Unicode characters")
        return value


class ReaderAnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["highlight", "underline", "comment"]
    view: Literal["pages", "text"] = "pages"
    page: int = Field(ge=1, le=10000)
    quote: ReaderQuote | None = None
    text: str = Field(default="", max_length=4000)

    _printable = field_validator("text")(ReaderQuote.printable.__func__)

    @model_validator(mode="after")
    def meaningful(self):
        if self.kind in ("highlight", "underline") and self.quote is None:
            raise ValueError("Select words to highlight or underline")
        if self.kind == "comment" and not self.text.strip():
            raise ValueError("Write a comment before saving")
        return self
