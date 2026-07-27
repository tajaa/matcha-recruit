"""Broker Pilot -- grounded per-client P&C analysis chat (Broker Pro).

The broker opens an analysis session for one client (on-platform company or
off-platform external client), uploads ad-hoc carrier documents (loss runs,
dec pages, competing quotes, carrier letters, bordereaux), and converses with
an AI grounded in BOTH the uploads and the platform data already on file
(`broker_submission._tenant_context` / `_external_context`).

Derived from the Legal Pilot architecture (`services/pilots/legal_defense/`) and
reuses its pure gates directly: `validate_citations` drops any cited ID not in
the corpus index before anything reaches the broker, and the memo PDF appendix
is rendered deterministically from DB rows / the re-gathered context -- never
from model text.

Corpus cid scheme (one flat index; the citation gate and memo renderer key on it):
- ``doc:<uuid>``            -- one record per uploaded document
- ``docfig:<uuid>.<n>``     -- one record per extracted key figure (minted from
                              the stored extraction JSONB, never per-turn)
- ``platform:<section>``    -- a section of the submission context (wc, epl, ...)
- ``platform:<section>.<sub>`` -- a specific factor/line/period within a section

Documents are processed once at upload (classify + extract + local text
extraction); chat turns never re-send file bytes. A Gemini failure at upload
degrades the document to ``text_only`` -- chat still grounds on the raw text.
Never raises on the analysis path -- failures degrade, they don't 500.

Facade package (refactor round 2, stage 6) over a 1,811-line flat module, split
on its own `# ---` banners. `routes/broker/pilot.py` imports this as `bp` and
reaches ~30 names by attribute, so everything is re-exported below.
"""
import logging

from ._config import (  # noqa: F401
    MODEL,
    _GEMINI_TIMEOUT,
    _HISTORY_TURNS,
    _DOC_TEXT_CAP,
    _MAX_DOC_TEXT_BLOCKS,
    _STORED_TEXT_CAP,
    _MAX_DOCS_PER_SESSION,
    _MAX_KEY_FIGURES,
    _MAX_NOTABLE,
    _MAX_QUESTIONS,
    _MAX_FINDINGS,
    _FINDING_POINT_CAP,
    _QUESTION_CAP,
    _GAP_SEVERITIES,
    DOC_TYPES,
    _LINES,
    DISCLAIMER,
)
from .templates import (  # noqa: F401
    PILOT_TEMPLATES,
    _TEMPLATE_BY_KEY,
    _lookup_template,
    _public_template,
    template_catalog,
    get_template,
    _mode_focus,
)
from .extraction import (  # noqa: F401
    _EXTRACT_PROMPT,
    _coerce_extraction,
    extract_document,
)
from .corpus import (  # noqa: F401
    _fmt_num,
    _clause_records,
    _FLEET_DRIVER_CAP,
    _platform_records,
    _doc_records,
    _NATIVE_PER_SOURCE_CAP,
    _BROKER_EXCLUDED_SOURCES,
    gather_native_sources,
    _jurisdiction_records,
    build_corpus,
)
from .chat import (  # noqa: F401
    _SYSTEM,
    _corpus_text,
    _history_text,
    _scope_text,
    _build_prompt,
    _coerce_findings,
    _coerce_turn,
    _gate,
    _why_empty,
    _generate_once,
    _generate,
    _is_empty_turn,
    run_chat_turn,
)
from .memo import (  # noqa: F401
    _cited_ids,
    _MEMO_CSS_EXTRA,
    _GONE,
    _doc_appendix_html,
    _platform_appendix_html,
    _native_appendix_html,
    _jurisdiction_appendix_html,
    _link_or_dash,
    _narrative_html,
    _memo_html,
    _render_pdf,
    build_memo_pdf,
)
"""Broker Pilot — grounded per-client P&C analysis chat (Broker Pro).

The broker opens an analysis session for one client (on-platform company or
off-platform external client), uploads ad-hoc carrier documents (loss runs,
dec pages, competing quotes, carrier letters, bordereaux), and converses with
an AI grounded in BOTH the uploads and the platform data already on file
(`broker_submission._tenant_context` / `_external_context`).

Derived from the Legal Pilot architecture (`services/legal_defense.py`) and
reuses its pure gates directly: `validate_citations` drops any cited ID not in
the corpus index before anything reaches the broker, and the memo PDF appendix
is rendered deterministically from DB rows / the re-gathered context — never
from model text.

Corpus cid scheme (one flat index; the citation gate and memo renderer key on it):
- ``doc:<uuid>``            — one record per uploaded document
- ``docfig:<uuid>.<n>``     — one record per extracted key figure (minted from
                              the stored extraction JSONB, never per-turn)
- ``platform:<section>``    — a section of the submission context (wc, epl, …)
- ``platform:<section>.<sub>`` — a specific factor/line/period within a section

Documents are processed once at upload (classify + extract + local text
extraction); chat turns never re-send file bytes. A Gemini failure at upload
degrades the document to ``text_only`` — chat still grounds on the raw text.
Never raises on the analysis path — failures degrade, they don't 500.
"""


logger = logging.getLogger(__name__)


# _genai / _hum / _slug were byte-identical copies of the services/_shared
# leaves (stage 2 deduped 6 other _genai copies but not this file's). Imported
# rather than redefined; re-exported because routes/broker/pilot.py reaches
# them as `bp._slug` etc.
from app.matcha.services._shared.gemini import _genai  # noqa: F401,E402
from app.matcha.services._shared.text import _hum, _slug  # noqa: F401,E402


