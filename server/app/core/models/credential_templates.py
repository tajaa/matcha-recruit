"""Request models for company credential catalog settings."""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CredentialTypeCreate(BaseModel):
    """Create a tenant-owned option in credential-type dropdowns."""

    label: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    description: str | None = Field(default=None, max_length=2000)
    has_expiration: bool = True
    has_number: bool = False
    has_state: bool = False

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("label cannot be empty")
        if "\x00" in value:
            raise ValueError("label contains an unsupported null character")
        if any(character in value for character in "\r\n\t"):
            raise ValueError("label must be a single line")
        return value

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "\x00" in value:
            raise ValueError("description contains an unsupported null character")
        return value.strip() or None


class CredentialTypeVisibilityUpdate(BaseModel):
    """Replace the credential types offered by this company to users."""

    # ``credential_types`` is a shared catalog that AI research keeps appending
    # to, so this bound only exists to cap the request body -- it must stay well
    # clear of the catalog size or selecting every type becomes unsaveable.  The
    # route rejects ids that are not real credential types anyway.
    credential_type_ids: list[UUID] = Field(default_factory=list, max_length=5000)
