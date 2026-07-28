"""Handbook Pilot — grounded conversational handbook/policy generation (Pro + Matcha-X).

A business admin opens a generation session and converses with an AI grounded in
the company's own material: the handbook profile, the jurisdiction/compliance
requirements that apply to the company's work locations (the same
`jurisdiction_requirements` corpus the template generator and the audit grader
read), the industry playbook baseline, and the company's existing handbook
sections + policies (so the pilot revises rather than duplicates). The model
proposes candidate handbook sections and standalone policies; every enforceable
clause must cite a bracketed corpus ID, and the shared
`legal_defense.validate_citations` gate drops any citation not in the corpus
before anything reaches the user. Proposed drafts persist as reviewable rows
that the admin edits and PROMOTES into the real handbooks / policies tables.

Derived from the Broker Pilot / Legal Pilot architecture
(`services/broker/broker_pilot/`, `services/pilots/legal_defense/`) and reuses
their pure gates directly. Never raises on the analysis path — failures degrade, not 500.

Corpus cid scheme (one flat index; the citation gate keys on it):
- ``profile``                        — the company handbook profile record
- ``law:<state>-<cat>-<title-slug>`` — one record per applicable jurisdiction requirement
- ``handbook:<uuid>``                — one record per existing handbook section
- ``policy:<uuid>``                  — one record per existing policy
- ``playbook:<slug>``                — one record per industry playbook baseline section
- ``floor:<level>-<juris>-<cat>``    — the GOVERNING requirement per category (precedence-resolved)
- ``audit:<state>-<req-key>``        — one record per open gap from the latest handbook audit
- ``fresh:<uuid>``                   — one record per finding from the latest freshness check

`audit:` / `fresh:` are findings ABOUT the handbook, not law — the prompt forbids
citing them as the source of an obligation, and `law_citation_count` (which
drives the grounded/amber dot) deliberately ignores them.

Law cids are derived from the requirement's *content* (state + category + title),
not its position in the fetch, because `_fetch_state_requirements` orders by
effective/updated date — a jurisdiction data refresh reorders the rows. Cids used
to carry the enumeration ordinal (`law:<state>-<cat>-<n>`), so a refresh silently
re-pointed every stored citation and cited requirements fell back to "uncovered".
Citations stored under that old scheme are recovered by `lookup_record`, which
matches on the `state-category` prefix when it names exactly one requirement.

Facade package (refactor round 2, stage 6) over a 1,556-line flat module, split
on the pure-vs-DB fault lines its own docstrings already labelled.
routes/pilots/handbook.py imports this as `hp` and reaches many names by
attribute, and hr_pilot_corpus.py imports `build_corpus` / `_floor_records` /
`_slug` directly, so everything is re-exported below.
"""
import logging

from ._config import (  # noqa: F401
    MODEL,
    _GEMINI_TIMEOUT,
    _HISTORY_TURNS,
    _LAW_PER_STATE_CAP,
    _MAX_EXISTING_SECTIONS,
    _MAX_EXISTING_POLICIES,
    _MAX_DRAFTS_PER_TURN,
    _CONTENT_CAP,
    _MAX_AUDIT_GAPS,
    _MAX_FRESHNESS_FINDINGS,
    _AUDIT_STALE_DAYS,
    DRAFT_KINDS,
    _SEVERITY_RANK,
    _FRESHNESS_LABELS,
    _FULL_TEXT_PER_RECORD,
    _FULL_TEXT_BUDGET,
    _SEVERITY_ORDER,
)
from .grounding import (  # noqa: F401
    gather_grounding,
    _fetch_audit_gaps,
    _fetch_freshness_findings,
    attach_compliance_floor,
)
from .corpus import (  # noqa: F401
    _profile_record,
    _law_records,
    _existing_section_records,
    _existing_policy_records,
    _playbook_records,
    _audit_records,
    _freshness_records,
    _floor_records,
    _full_text_map,
    build_corpus,
    _LEGACY_LAW_CID,
    lookup_record,
    _legacy_prefix,
    canonical_cid,
)
from .chat import (  # noqa: F401
    _SYSTEM,
    _corpus_text,
    _history_text,
    _build_prompt,
    _INLINE_CID,
    strip_corpus_citations,
    _coerce_drafts,
    _generate,
    run_chat_turn,
)
from .assembly import (  # noqa: F401
    _coerce_cid_list,
    resolve_citations,
    _assemble_draft,
    _floor_coverage,
    _floor_citers,
    assemble_handbook,
)
from .scan import (  # noqa: F401
    _dedupe_matched,
    _sort_gaps_by_severity,
    _empty_scan,
    run_compliance_scan,
)
from .persistence import (  # noqa: F401
    unpaid_x_reason,
    persist_turn,
    promote_drafts,
    _fresh_cids_from_drafts,
)

logger = logging.getLogger(__name__)


# _genai / _slug / _hum were byte-identical copies of the services/_shared
# leaves. Imported rather than redefined; re-exported because
# hr_pilot_corpus.py imports `_slug` from this package by name.
from app.matcha.services._shared.gemini import _genai  # noqa: F401
from app.matcha.services._shared.text import _hum, _slug  # noqa: F401


