"""What a person can tell a research task up front, and its check.

Everything is optional: the directive alone is enough ("best organic lip
balm under $15"). What is given here is fact, not a model's reading of the
directive, so the plan can't drop it: a budget becomes a hard constraint, a
place goes into every query.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..playbook import IntakeField


def _clean_list(values: list[str], limit: int) -> list[str]:
    out, seen = [], set()
    for value in values:
        text = " ".join(str(value).split())[:limit]
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


class ResearchBrief(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    location: str | None = Field(default=None, max_length=120)
    budget_min: float | None = Field(default=None, gt=0, le=10_000_000)
    budget_max: float | None = Field(default=None, gt=0, le=10_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    must_haves: list[str] = Field(default_factory=list, max_length=10)
    nice_to_haves: list[str] = Field(default_factory=list, max_length=10)
    avoid: list[str] = Field(default_factory=list, max_length=10)
    needed_by: date | None = None

    @field_validator("must_haves", "nice_to_haves", "avoid")
    @classmethod
    def short_items(cls, values):
        return _clean_list(values, 120)

    @field_validator("location")
    @classmethod
    def one_line(cls, value):
        return " ".join(value.split()) or None if value else None

    @model_validator(mode="after")
    def budget_range(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("The budget's low end is above its high end.")
        return self

    @field_validator("currency")
    @classmethod
    def code(cls, value):
        value = value.upper()
        if not value.isalpha():
            raise ValueError("Use a three-letter currency code, like USD.")
        return value


class ApartmentBrief(ResearchBrief):
    """A home to rent: what a listing has to have, as limits. `near` is a place
    distances are measured from ("Lady Bird Lake"); the miles and directions
    are limits on that distance, so they need it."""

    beds_min: float | None = Field(default=None, ge=0, le=10)
    baths_min: float | None = Field(default=None, ge=0, le=10)
    pets: list[Literal["dogs", "cats"]] = Field(default_factory=list, max_length=2)
    move_in: date | None = None
    near: str | None = Field(default=None, max_length=120)
    min_miles: float | None = Field(default=None, ge=0, le=200)
    max_miles: float | None = Field(default=None, gt=0, le=200)
    directions: list[Literal["north", "east", "south", "west"]] = Field(default_factory=list, max_length=4)

    @field_validator("near")
    @classmethod
    def near_one_line(cls, value):
        return " ".join(value.split()) or None if value else None

    @model_validator(mode="after")
    def distance_needs_a_place(self):
        if (self.min_miles is not None or self.max_miles is not None or self.directions) and not self.near:
            raise ValueError("Say where the distance is measured from (near).")
        if self.min_miles is not None and self.max_miles is not None and self.min_miles > self.max_miles:
            raise ValueError("The least distance is more than the most.")
        if len(set(self.directions)) == 4:
            self.directions = []  # every direction is no limit
        return self


def validator(model: type[ResearchBrief]) -> Callable[[dict[str, Any]], dict]:
    """A playbook's `validate_brief` over this brief model."""
    def validate(raw: dict[str, Any]) -> dict:
        """The brief as stored, or ValueError with what to fix."""
        try:
            brief = model.model_validate(raw or {})
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first.get("loc") or ()) or "brief"
            raise ValueError(f"{where}: {first.get('msg')}") from exc
        return brief.model_dump(mode="json", exclude_none=True)

    return validate


validate_brief = validator(ResearchBrief)


INTAKE = (
    IntakeField(key="location", label="Where", type="location", help="A city, neighborhood or address"),
    IntakeField(key="budget_max", label="Budget (max)", type="money"),
    IntakeField(key="budget_min", label="Budget (min)", type="money", ask="never"),
    IntakeField(key="must_haves", label="Must have", type="list"),
    IntakeField(key="nice_to_haves", label="Nice to have", type="list"),
    IntakeField(key="avoid", label="Avoid", type="list"),
    IntakeField(key="needed_by", label="Needed by", type="date", ask="never"),
    IntakeField(key="reference_files", label="Reference files", type="file", ask="never",
                accept=("document", "image"), max_count=3, max_bytes=10 * 1024 * 1024,
                help="A photo of what you want, a spec sheet, a list"),
)
