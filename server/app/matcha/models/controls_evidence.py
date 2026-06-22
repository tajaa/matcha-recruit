"""Controls-evidence register models."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

ControlStatus = Literal["strong", "partial", "gap", "na"]


class ControlEvidenceUpdate(BaseModel):
    """Per-control verification override the company/broker records on top of the
    auto-computed register. ``status=None`` keeps the auto-computed status;
    ``verified=True`` stamps ``verified_at = now()``."""

    status: Optional[ControlStatus] = None
    note: Optional[str] = Field(None, max_length=2000)
    verified: bool = False
