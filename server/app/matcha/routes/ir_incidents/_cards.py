"""Thin re-export shim (refactor round 2, stage 3) — the real IR Copilot card
builders moved to ``app.matcha.services.ir.ir_cards``. Kept so
``from ._cards import build_osha_...`` inside this package, and
``_shared.py``'s re-export of the same names, keep working unchanged.
"""
from app.matcha.services.ir.ir_cards import (  # noqa: F401
    OSHA_INJURY_TYPES,
    OSHA_INJURY_TYPE_LABELS,
    OSHA_EMERGENCY_ALERT_CARD_ID,
    OSHA_EMERGENCY_HOTLINE,
    OSHA_REPORTING_WINDOW,
    ROOT_CAUSE_INTERVIEW_STEPS,
    ROOT_CAUSE_PROMPTS,
    ROOT_CAUSE_PLAINTEXT_LABELS,
    build_osha_emergency_alert_card,
    build_osha_recordable_query_card,
    build_osha_days_type_query_card,
    build_osha_days_count_card,
    build_osha_injury_type_query_card,
    build_privacy_case_query_card,
    build_log_root_cause_query_card,
    build_root_cause_text_card,
    build_root_cause_logged_ack_card,
    compose_root_cause_text,
    build_osha_close_confirmation_card,
    build_treatment_query_card,
    build_request_documents_card,
    build_investigation_notes_card,
    build_osha_clean_description_card,
    build_assign_training_card,
)
