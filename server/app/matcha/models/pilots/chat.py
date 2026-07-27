"""The shared pilot chat-turn request body.

Four pilot surfaces (Broker, Handbook, Legal, Analysis) each defined a `ChatIn`
with the identical single `message` field; the Analysis one additionally
carries `focus` (the highlight-to-chat cid list). One base here, subclassed
where a surface genuinely needs more.

Deliberately NOT extended to `SessionCreate` / `SessionUpdate`, which the same
four surfaces also each define: those share only `title` and `status` and
otherwise diverge completely (broker carries subject_kind/subject_id/
template_key, handbook goal/industry, analysis domain/goal). A base for two
fields would add indirection without removing duplication.
"""
from pydantic import BaseModel, Field


class PilotChatIn(BaseModel):
    """One user turn in a grounded pilot chat."""

    message: str = Field(..., min_length=1, max_length=5000)
