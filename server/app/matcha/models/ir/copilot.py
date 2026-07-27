"""IR Copilot card, message, progress and transcript shapes. Consumed by
routes/ir_incidents/copilot.py.
"""
from datetime import datetime
from typing import Optional, Literal, Any
from uuid import UUID
from pydantic import BaseModel, Field

from ._types import IRCopilotActionType, IRCopilotMessageType, IRCopilotRole



class IRCopilotChoice(BaseModel):
    label: str
    value: str


class IRCopilotCardAction(BaseModel):
    type: IRCopilotActionType
    label: str
    tab: Optional[str] = None
    analysis_type: Optional[str] = None
    field_name: Optional[str] = None
    field_value: Optional[Any] = None
    search_query: Optional[str] = None
    # quick_reply: button picker. quick_reply_kind discriminates the OSHA chain step.
    choices: Optional[list[IRCopilotChoice]] = None
    quick_reply_kind: Optional[str] = None
    # numeric_input / text_input: validated input field. target_field names
    # the incident column or JSONB key to write to; pending_classification
    # carries the osha_classification value to set alongside (days_away vs
    # restricted_duty). text_input also uses prompt_text + input_rows for
    # the textarea label + height.
    target_field: Optional[str] = None
    pending_classification: Optional[str] = None
    input_label: Optional[str] = None
    input_min: Optional[int] = None
    input_max: Optional[int] = None
    prompt_text: Optional[str] = None
    input_rows: Optional[int] = None
    # text_input: pre-filled textarea value (e.g. the AI-cleansed OSHA 300
    # description draft, or the raw narrative for the human to strip names from).
    # MUST be declared here — _extract_current_cards round-trips the persisted
    # card through this model, so an undeclared field is dropped before the FE
    # ever sees it (blank textarea bug).
    prefilled: Optional[str] = None
    # osha_emergency_alert: informational + acknowledgment.
    phone: Optional[str] = None
    deadline: Optional[str] = None
    # assign_training: requirement to assign + optional explicit trainee list
    # (unset => defaults to the incident's involved_employee_ids at accept
    # time, same default as POST /assign-training).
    requirement_id: Optional[UUID] = None
    employee_ids: Optional[list[UUID]] = None


class IRCopilotCard(BaseModel):
    id: str
    title: str
    recommendation: str
    rationale: str
    priority: Literal["high", "medium", "low"] = "medium"
    blockers: list[str] = []
    action: IRCopilotCardAction
    interview_questions: Optional[list[str]] = None


class IRCopilotMessage(BaseModel):
    id: UUID
    role: IRCopilotRole
    message_type: IRCopilotMessageType = "text"
    content: str
    metadata: Optional[dict[str, Any]] = None
    created_by: Optional[UUID] = None
    created_at: datetime


class IRCopilotProgressStep(BaseModel):
    key: str
    label: str
    status: Literal["done", "pending", "not_applicable"]
    hint: str = ""


class IRCopilotProgress(BaseModel):
    """How much of the Copilot flow is left. Computed by
    ``services/ir_flow.close_progress`` from the same predicates that gate
    closing, so the meter and the Close button always agree."""
    completed: int = 0
    total: int = 0
    percent: int = 0
    steps: list[IRCopilotProgressStep] = []
    next_step_key: Optional[str] = None
    next_step_hint: str = ""
    is_complete: bool = False


class IRCopilotEvidence(BaseModel):
    """Preponderance-of-evidence + duration tracker. Computed by
    ``services/ir_flow.copilot_evidence``, mirroring the ER Copilot's
    evidence-confidence banner (``determination_confidence``) applied to the
    incident-reporting workflow, plus a severity-scaled days-open ceiling so
    an investigation can't run indefinitely unnoticed."""
    score: int = 0
    threshold: int = 80
    sufficient: bool = False
    signals: list[str] = []
    missing: list[str] = []
    days_open: int = 0
    max_days: int = 30
    is_overdue: bool = False


class IRCopilotTranscript(BaseModel):
    incident_id: UUID
    messages: list[IRCopilotMessage]
    current_cards: list[IRCopilotCard] = []
    summary: Optional[str] = None
    open_questions: list[str] = []
    progress: Optional[IRCopilotProgress] = None
    evidence: Optional[IRCopilotEvidence] = None


class IRCopilotStreamRequest(BaseModel):
    message: Optional[str] = Field(default=None, max_length=4000)


class IRCopilotAcceptRequest(BaseModel):
    message_id: UUID
    card_id: str
    # quick_reply: which choice the user picked.
    selected_value: Optional[str] = None
    # numeric_input: the validated number the user typed.
    numeric_value: Optional[int] = None
    # text_input: free-text answer (root-cause interview steps).
    text_value: Optional[str] = Field(default=None, max_length=4000)
    # osha_emergency_alert: user's confirmation notes (required to clear the block).
    notes: Optional[str] = Field(default=None, max_length=2000)
