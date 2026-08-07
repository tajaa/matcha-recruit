import uuid
from typing import Literal

from pydantic import BaseModel


class IssueSchema(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    field: str | None = None
    track_id: uuid.UUID | None = None


class ValidationReportSchema(BaseModel):
    packageable: bool
    issues: list[IssueSchema]
