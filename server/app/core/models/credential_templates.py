"""Request models for company credential catalog settings."""

from uuid import UUID

from pydantic import BaseModel, Field


class CredentialTypeVisibilityUpdate(BaseModel):
    """Replace the credential types offered by this company to users."""

    credential_type_ids: list[UUID] = Field(default_factory=list, max_length=100)
