"""Matcha Work AI service -- facade package.

Split (refactor round 2, stage 6) from a 1,893-line flat module: ~370 of those
lines were raw prompt literals and 795 were GeminiProvider, so editing either
meant scrolling past the other.

Callers reach this package both ways -- `from ...matcha_work_ai import X` and
attribute access on the module object -- so every name is re-exported below
with `# noqa: F401` and no caller changed. Do not prune a re-export without
re-grepping; several are imported by exactly one route file.

Module-level mutable state (the context-cache registry, the provider singleton)
lives in provider.py, NOT here -- re-exporting a name does not alias the
binding, so a rebind here would not be seen by the code that reads it.
"""
import logging
from cachetools import TTLCache  # noqa: E402

from ._images import (  # noqa: F401
    _IMAGE_FETCH_TIMEOUT,
    _MAX_IMAGE_BYTES,
    _EXT_MIME,
    _is_trusted_image_url,
    _fetch_image_bytes,
    fetch_image_parts_for_messages,
)
from ._fields import (  # noqa: F401
    OFFER_LETTER_FIELDS,
    REVIEW_FIELDS,
    WORKBOOK_FIELDS,
    ONBOARDING_FIELDS,
    PRESENTATION_FIELDS,
    HANDBOOK_UPLOAD_MANAGED_FIELDS,
    HANDBOOK_FIELDS,
    POLICY_FIELDS,
    PROJECT_FIELDS,
    BLOG_FIELDS,
    HR_PILOT_FIELDS,
    SUPPORTED_AI_MODES,
    SUPPORTED_AI_SKILLS,
    SUPPORTED_AI_OPERATIONS,
)
from ._prompts import (  # noqa: F401
    MATCHA_WORK_BLOG_STATIC_PROMPT,
    MATCHA_WORK_BLOG_DYNAMIC_PROMPT,
    PAYER_MODE_SYSTEM_PROMPT,
    MATCHA_WORK_STATIC_PROMPT_TEMPLATE,
    MATCHA_WORK_DYNAMIC_PROMPT_TEMPLATE,
    MATCHA_WORK_SYSTEM_PROMPT_TEMPLATE,
)
from ._text import (  # noqa: F401
    _build_company_context,
    _clean_json_text,
    _extract_reply_field,
    _infer_skill_from_state,
)
from ._models import (  # noqa: F401
    SUPPORTED_MODELS,
    PRO_MODEL,
    _get_model,
    _HIGH_THINK_KEYWORDS,
    _TRIVIAL_PATTERNS,
    classify_thinking_level,
)
from .provider import (  # noqa: F401
    _GOOGLE_SEARCH_TOOL,
    GEMINI_CALL_TIMEOUT,
    _CACHE_TTL_SECONDS,
    _CACHE_REGISTRY_MAX,
    _cache_registry,
    _cache_creation_lock,
    _cache_unsupported_models,
    AIResponse,
    MatchaWorkAIProvider,
    GeminiProvider,
    _provider,
    get_ai_provider,
)
from .compaction import (  # noqa: F401
    COMPACTION_PROMPT,
    COMPACTION_MODEL,
    COMPACTION_THRESHOLD,
    COMPACTION_INPUT_MESSAGE_CAP,
    compact_conversation,
)
from .task_draft import (  # noqa: F401
    _TASK_DRAFT_PRIORITIES,
    _TASK_DRAFT_CATEGORIES,
    _TASK_DRAFT_COLUMNS,
    generate_task_draft,
)


logger = logging.getLogger(__name__)


# ── Gemini Context Cache Registry ──
# Maps (company_id + prompt_hash + model) → (cache_name, model). TTL+LRU
# eviction prevents unbounded growth on a long-running server with many
# tenants. Bounded to ~companies × prompt-variants × models.


