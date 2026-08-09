import uuid

from pydantic import BaseModel, ConfigDict

from app.oceanlab.models.enums import CodeSource


class LabelSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_artist_id: uuid.UUID | None
    default_contributor_id: uuid.UUID | None
    default_genre: str | None
    default_territories: str
    c_line_template: str
    p_line_template: str
    isrc_source: CodeSource
    upc_source: CodeSource


class LabelSettingsUpdate(BaseModel):
    """Every field optional — PATCH semantics on a PUT, because the client
    edits one section of the Settings page at a time. `exclude_unset` at the
    callsite is what makes an omitted field mean "leave alone" rather than
    "set to null"."""

    default_artist_id: uuid.UUID | None = None
    default_contributor_id: uuid.UUID | None = None
    default_genre: str | None = None
    default_territories: str | None = None
    c_line_template: str | None = None
    p_line_template: str | None = None
    isrc_source: CodeSource | None = None
    upc_source: CodeSource | None = None
