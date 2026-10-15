"""Bounded bodies for the Espresso Tasks REST API."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ItemState = Literal["new", "saved", "dismissed", "chosen"]
RoundKind = Literal["refine", "more", "document"]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentTaskCreate(Body):
    request_id: UUID
    playbook: str = Field(default="research", pattern=r"^[a-z][a-z_]{0,39}$")
    directive: str = Field(min_length=3, max_length=4000)
    title: str = Field(default="", max_length=120)
    # Checked by the playbook's own `validate_brief`.
    brief: dict[str, Any] = Field(default_factory=dict)
    # Files the person gave it (`mw_agent_inputs`, their own).
    input_ids: list[UUID] = Field(default_factory=list, max_length=5)
    # The playbook's disclosure version the person just agreed to, when they had not yet.
    consent_version: str | None = Field(default=None, max_length=40)


class RoundCreate(Body):
    request_id: UUID
    kind: RoundKind
    directive: str = Field(default="", max_length=2000)
    # "More like these" for `more`; which findings a `document` covers.
    item_ids: list[UUID] = Field(default_factory=list, max_length=20)


class ItemPatch(Body):
    user_state: ItemState | None = None
    notes: str | None = Field(default=None, max_length=4000)


class FormAnswer(Body):
    """A submitted `ask_form`: field key -> value, and the files for its file fields."""

    values: dict[str, Any] = Field(default_factory=dict)
    input_ids: list[UUID] = Field(default_factory=list, max_length=5)
    consent_version: str | None = Field(default=None, max_length=40)
