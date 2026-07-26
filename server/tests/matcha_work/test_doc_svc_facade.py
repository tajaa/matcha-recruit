"""matcha_work_document facade smoke tests — pure attribute checks, no DB.

Guards the 2026-07 (L7) split of matcha_work_document/__init__.py into
domain submodules: every attribute external code reaches via `doc_svc.X` or a
named import must still resolve off the package, and the company-profile
cache singleton must not have been duplicated across modules.
"""
from app.matcha.services.matcha_work import matcha_work_document as doc_svc
from app.matcha.services.matcha_work.matcha_work_document import _profile


_EXTERNAL_ATTRS = [
    "add_message", "apply_update", "build_matcha_work_thread_storage_prefix",
    "check_token_quota", "create_thread", "ensure_matcha_work_thread_storage_scope",
    "finalize_thread", "generate_cover_image", "generate_pdf",
    "generate_presentation_pdf", "generate_workbook_presentation",
    "get_company_profile_for_ai", "get_context_summary", "get_public_review_request",
    "get_thread", "get_thread_message_count", "get_thread_messages",
    "get_token_usage_summary", "list_elements", "list_review_requests",
    "list_threads", "list_versions", "log_token_usage_event",
    "normalize_recipient_emails", "revert_to_version", "save_context_summary",
    "save_offer_letter_draft", "send_offer_letter_draft", "send_review_requests",
    "set_thread_compliance_mode", "set_thread_mode", "set_thread_node_mode",
    "set_thread_payer_mode", "set_thread_pinned", "submit_public_review_request",
    "sync_element_record",
    # named-import-only externals
    "invalidate_company_profile_cache",
    "_sync_element_for_thread",
    "_company_profile_cache",
]


def test_facade_exposes_every_external_attribute():
    missing = [a for a in _EXTERNAL_ATTRS if not hasattr(doc_svc, a)]
    assert missing == [], f"facade missing attrs: {missing}"


def test_company_profile_cache_is_one_singleton():
    """The TTLCache must be instantiated exactly once (in _profile) — a
    second instantiation anywhere would silently split cache invalidation."""
    assert doc_svc._company_profile_cache is _profile._company_profile_cache
    assert doc_svc.invalidate_company_profile_cache is _profile.invalidate_company_profile_cache
    assert doc_svc.get_company_profile_for_ai is _profile.get_company_profile_for_ai
