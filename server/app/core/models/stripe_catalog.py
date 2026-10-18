"""Admin-editable Stripe catalog presentation; IDs and prices stay server-owned."""
from pydantic import BaseModel, Field, field_validator


class StripeCatalogDetails(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Product name cannot be blank")
        return value.strip()
