"""Matcha Work document service — facade package.

Split (L7) from a 2,057-line single __init__.py into domain submodules.
External callers reach this package two ways: attribute access on the module
object (`from app.matcha.services.matcha_work import matcha_work_document as
doc_svc`, then `doc_svc.X`) or named imports (`from
app.matcha.services.matcha_work.matcha_work_document import X`). Every name
below is load-bearing for one or both — do not prune without re-grepping.

Leaf helpers (_coerce/_storage/_email_html/_tokens) predate this split (L6)
and are re-imported unchanged.
"""

# Leaf helpers extracted to submodules (L6). Re-imported so this module's own
# code + external `doc_svc.X` callers keep working.
from app.matcha.services.matcha_work.matcha_work_document._coerce import (  # noqa: F401
    EMAIL_REGEX,
    VALID_REVIEW_REQUEST_STATUSES,
    _parse_jsonb,
    _infer_skill_from_state,
    _strip_markdown_text,
    _extract_slide_bullets,
    _build_workbook_presentation_state,
    _parse_date_str,
    _coerce_bool,
    _coerce_int,
    _coerce_float,
    _coerce_datetime,
    _normalize_email,
    normalize_recipient_emails,
    _coerce_state_recipient_emails,
    _coerce_offer_draft_recipient_emails,
    _row_to_review_request_status,
    _build_review_request_state_update,
)
from app.matcha.services.matcha_work.matcha_work_document._storage import (  # noqa: F401
    MATCHA_WORK_STORAGE_ROOT,
    _should_enforce_company_scoped_matcha_work_storage,
    build_matcha_work_thread_storage_prefix,
    _storage_key_from_path,
    _storage_path_has_prefix,
    _storage_filename,
    _migrate_matcha_work_asset_to_scope,
    ensure_matcha_work_thread_storage_scope,
)
from app.matcha.services.matcha_work.matcha_work_document._email_html import (  # noqa: F401
    _render_review_request_email_html,
    _render_offer_letter_draft_email_html,
    _build_offer_letter_payload,
)
from app.matcha.services.matcha_work.matcha_work_document._tokens import (  # noqa: F401
    _DEFAULT_TOKEN_LIMIT,
    _DEFAULT_WINDOW_HOURS,
    log_token_usage_event,
    check_token_quota,
    get_token_usage_summary,
)

# Domain submodules (L7 split). External callers use doc_svc.X attribute
# access or named imports — every name below is load-bearing; do not prune.
from ._profile import (  # noqa: F401
    _company_profile_cache,  # singleton — lives in _profile; re-bound here for attr parity
    invalidate_company_profile_cache,
    get_company_profile_for_ai,
)
from .context import (  # noqa: F401
    get_thread_message_count,
    get_context_summary,
    save_context_summary,
)
from .threads import (  # noqa: F401
    create_thread,
    get_thread,
    _thread_list_item_from_row,
    list_threads,
)
from .elements import (  # noqa: F401
    VALID_ELEMENT_TYPES,
    list_elements,
    _upsert_element_from_thread_row,
    _sync_element_for_thread,
    sync_element_record,
)
from .modes import (  # noqa: F401
    set_thread_pinned,
    set_thread_mode,
    set_thread_node_mode,
    set_thread_compliance_mode,
    set_thread_payer_mode,
)
from .messages import get_thread_messages, add_message  # noqa: F401
from .versions import apply_update, revert_to_version, list_versions  # noqa: F401
from .pdf import (  # noqa: F401
    _get_cached_pdf_url,
    _cache_pdf_url,
    generate_pdf,
    _render_presentation_html,
    generate_presentation_pdf,
    generate_cover_image,
)
from .offer_letters import save_offer_letter_draft, send_offer_letter_draft  # noqa: F401
from .workbook import generate_workbook_presentation, finalize_thread  # noqa: F401
from .review_requests import (  # noqa: F401
    _list_review_requests_for_thread,
    list_review_requests,
    sync_review_request_state,
    send_review_requests,
    get_public_review_request,
    submit_public_review_request,
)
