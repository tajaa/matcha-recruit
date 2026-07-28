"""Shared `Literal` type aliases for the IR models.

Kept in one leaf module rather than duplicated into each submodule: several are
used by more than one group (`IRIncidentType` by both `incident` and the
services layer, the CorrectiveAction* set by `capa`), and a divergent copy of
one of these would be a silent contract change on a legal record.
"""
from typing import Literal


# Incident
IRIncidentType = Literal["safety", "behavioral", "property", "near_miss", "other"]
IRSeverity = Literal["critical", "high", "medium", "low"]
IRStatus = Literal["reported", "investigating", "action_required", "resolved", "closed"]
IRDocumentType = Literal["photo", "form", "statement", "other"]
IRAnalysisType = Literal["categorization", "severity", "root_cause", "recommendations", "similar", "consistency", "company_consistency", "policy_mapping"]

# People
IRPersonRole = Literal["reporter", "involved", "witness", "interviewee"]

# Corrective actions (CAPA)
CorrectiveActionType = Literal["corrective", "preventive", "training"]
CorrectiveActionPriority = Literal["immediate", "short_term", "long_term"]
CorrectiveActionStatus = Literal["open", "in_progress", "completed", "verified", "cancelled"]
CorrectiveActionEffectiveness = Literal["effective", "ineffective", "pending"]

# Copilot
IRCopilotRole = Literal["user", "assistant", "system"]
IRCopilotMessageType = Literal["text", "card", "event"]
IRCopilotActionType = Literal[
    "run_analysis", "set_field", "request_info", "escalate", "close_incident",
    "quick_reply", "numeric_input", "text_input", "osha_emergency_alert",
    "request_documents", "assign_training",
]
