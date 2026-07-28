"""Per-skill document field whitelists plus the supported mode / skill / operation
vocabularies. Pure data -- what the AI is allowed to write, per document type.
"""
import logging
from app.matcha.models.matcha_work.matcha_work import HandbookDocument, OfferLetterDocument, OnboardingDocument, PolicyDocument, PresentationDocument, ProjectDocument, ReviewDocument, WorkbookDocument

logger = logging.getLogger(__name__)


OFFER_LETTER_FIELDS = list(OfferLetterDocument.model_fields.keys())


REVIEW_FIELDS = list(ReviewDocument.model_fields.keys())


WORKBOOK_FIELDS = list(WorkbookDocument.model_fields.keys())


ONBOARDING_FIELDS = list(OnboardingDocument.model_fields.keys())


PRESENTATION_FIELDS = list(PresentationDocument.model_fields.keys())


HANDBOOK_UPLOAD_MANAGED_FIELDS = {
    "handbook_source_type",
    "handbook_upload_status",
    "handbook_uploaded_file_url",
    "handbook_uploaded_filename",
    "handbook_blocking_error",
    "handbook_review_locations",
    "handbook_red_flags",
    "handbook_green_flags",
    "handbook_jurisdiction_summaries",
    "handbook_analysis_generated_at",
    "handbook_strength_score",
    "handbook_strength_label",
    "handbook_analysis_progress",
}


HANDBOOK_FIELDS = [
    field_name for field_name in HandbookDocument.model_fields.keys()
    if field_name not in HANDBOOK_UPLOAD_MANAGED_FIELDS
]


POLICY_FIELDS = list(PolicyDocument.model_fields.keys())


PROJECT_FIELDS = list(ProjectDocument.model_fields.keys())


# Blog directive keys — these are NOT persisted to thread state.
# They're stripped before apply_update and handled in _apply_ai_updates_and_operations.
BLOG_FIELDS = [
    "blog_outline",
    "blog_section_draft",
    "blog_section_revision",
    "blog_title_suggestions",
    "blog_sections_replace",
]


# HR Pilot's single staged-action key. The proposal lives under one nested
# object so it round-trips through thread state as one whitelisted field.
HR_PILOT_FIELDS = ["hr_action"]


SUPPORTED_AI_MODES = {"skill", "general", "clarify", "refuse"}


SUPPORTED_AI_SKILLS = {"chat", "offer_letter", "review", "workbook", "onboarding", "presentation", "handbook", "policy", "resume_batch", "inventory", "project", "blog", "hr_pilot", "none"}


SUPPORTED_AI_OPERATIONS = {
    "create",
    "update",
    "save_draft",
    "send_draft",
    "finalize",
    "send_requests",
    "track",
    "create_employees",
    "generate_presentation",
    "generate_handbook",
    "generate_policy",
    "execute_hr_action",
    "none",
}
