"""Request models for company credential catalog settings."""

from uuid import UUID

from pydantic import BaseModel, Field


class CredentialTypeVisibilityUpdate(BaseModel):
    """Replace the credential types offered by this company to users."""

    # ``credential_types`` is a shared catalog that AI research keeps appending
    # to, so this bound only exists to cap the request body -- it must stay well
    # clear of the catalog size or selecting every type becomes unsaveable.  The
    # route rejects ids that are not real credential types anyway.
    credential_type_ids: list[UUID] = Field(default_factory=list, max_length=5000)
