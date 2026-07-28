"""Project service — CRUD + section management for mw_projects.
Facade package (refactor round 2, stage 6) over a 1,711-line flat module, split
by entity. Everything is re-exported here, so all 13 callers are unchanged.
"""
import logging

from ._config import (  # noqa: F401
    _compute_blog_stats,
    _ALLOWED_PROJECT_TYPES,
    PROJECT_TEMPLATE_SECTIONS,
    _ALLOWED_BLOG_TONES,
    _ALLOWED_BLOG_STATUSES,
    _ALLOWED_DISCIPLINE_LEVELS,
    _ALLOWED_DISCIPLINE_CATEGORIES,
    _ALLOWED_DISCIPLINE_SEVERITIES,
    _slugify,
    _HISTORY_SNAPSHOT_INTERVAL_SEC,
    _HISTORY_MAX_ENTRIES,
    _now_iso,
    _URL_RE,
    _URL_TRAILING,
)
from ._data import (  # noqa: F401
    _parse_project,
    _load_and_lock_data,
    _persist_data,
    get_project_raw,
)
from .crud import (  # noqa: F401
    _seed_blog_data,
    create_project,
    get_project,
    list_projects,
    update_project,
    archive_project,
    unarchive_project,
    delete_project_permanent,
    update_project_data,
    add_candidates_to_project,
    toggle_shortlist,
    toggle_dismiss,
    set_project_pin,
    search_admin_users,
)
from .sections import (  # noqa: F401
    _sections_from_row,
    _resolve_actor_name,
    _maybe_append_history,
    _mutate_sections,
    _update_sections,
    get_sections,
    add_section,
    update_section,
    accept_section_revision,
    reject_section_revision,
    delete_section,
    reorder_sections,
)
from .blog import (  # noqa: F401
    patch_blog,
    transition_blog_status,
    apply_blog_directives,
)
from .discipline import (  # noqa: F401
    _seed_discipline_data,
    patch_discipline,
    mark_discipline_meeting_held,
    record_discipline_signature_request,
    record_discipline_signed,
    record_discipline_refused,
)
from .collaborators import (  # noqa: F401
    create_project_chat,
    list_project_chats,
    get_project_as_collaborator,
    list_collaborators,
    ensure_discussion_channel,
    list_project_links,
    add_collaborator,
    ensure_collaborator_in_discussion_channel,
    remove_collaborator,
)

logger = logging.getLogger(__name__)


# ── Blog operations ──


# ── Recruiting-specific operations ──


# ── Collaborator operations ──


