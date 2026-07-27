"""Legal Defense builder — litigation-readiness evidence assembly.

For full-platform (Pro) SMBs that lack in-house counsel: when a legal stressor
hits (subpoena / class action / EEOC / audit), this assembles the company's OWN
records — already in Matcha across IR/OSHA, ER, compliance, discipline, training,
handbooks, accommodations + the immutable ``*_audit_log`` trails — into an
attorney-facing evidence packet. The win is cutting the hourly cost their outside
counsel would spend reconstructing the factual record.

Framing is deliberate: the AI is an **organizer, not an advocate**. It surfaces
WHAT THE RECORDS SHOW and flags gaps as open questions; it renders no verdict and
no liability opinion (a company-authored "we did nothing wrong" memo is
discoverable + unprivileged and can help a plaintiff). Grounding is enforced:
the model may cite only record IDs from the retrieved corpus, and
``validate_citations`` drops any hallucinated ID; the PDF appendix is rendered
deterministically from DB rows, never from model text.

Reuses ``claims_readiness`` (per-record IR/ER builders + PDF style),
``core.services.pdf.safe_url_fetcher`` (SSRF-guarded WeasyPrint), and
``core.services.storage`` (S3 fetch for the ZIP bundle). Never raises on the
read/gather path — a dead subsystem degrades to "unavailable", never a 500.
"""

# Package split 2026-07-25 (was a single 2,592-line module). Public surface is
# unchanged: every name is re-exported here so `from ...services import
# legal_defense as ld` and `from ..pilots.legal_defense import validate_citations`
# keep working. Tests that monkeypatch internals target the submodule (e.g.
# ``ld.chat._generate``), since a patch on the package attribute would not be
# seen by intra-module callers.

from ._shared import (  # noqa: F401
    DISCLAIMER,
    MODEL,
    _ACRONYM_LABELS,
    _GEMINI_TIMEOUT,
    _HISTORY_TURNS,
    _MAX_INTAKE_REQUESTS,
    _PER_SOURCE_CAP,
    _dt,
    _dt_date,
    _emp_name,
    _genai,
    _hum,
    _hum_acronym,
    _iso,
    _money,
    _parse_json,
)
from .theory import (  # noqa: F401
    BROAD_THEORY,
    _BROAD,
    _CLASSIFY_EXCLUDE_KEYWORDS,
    _CLASSIFY_ONLY_KEYWORDS,
    _CLASSIFY_PROBES,
    _COMPLIANCE_CATEGORIES,
    _EEO,
    _ER_CATEGORIES,
    _GENERIC_ER_CATEGORIES,
    _GENERIC_INFRACTIONS,
    _INCIDENT_TYPES,
    _INFRACTIONS,
    _MATTER_TYPE_THEORY,
    _OFF_THEORY_KEYWORDS,
    _OFF_THEORY_PROBES,
    _SAFETY,
    _STRONG_OVERRIDE,
    _STRONG_TYPE_PRIORS,
    _THEORIES,
    _THEORY_KEYWORDS,
    _THEORY_PROBES,
    _WAGE_HOUR,
    _Topic,
    _compile_probes,
    _demote_off_subject,
    _is_signalless,
    _matches_other_subject,
    _names_unmodeled_subject,
    resolve_matter_theory,
)
from .sources import (  # noqa: F401
    _UUID_RE_SQL,
    _scope_direct,
    _scope_employee,
    _scope_er_involved,
    _overdue_sql,
    _src_accommodations,
    _src_agency_charges,
    _src_biometric_consent,
    _src_compliance,
    _src_compliance_alerts,
    _src_compliance_remediation,
    _src_discipline,
    _src_er_cases,
    _src_hiring_ai_audits,
    _src_incidents,
    _src_leave,
    _src_pay_equity,
    _src_pay_transparency,
    _src_policy_ack,
    _src_post_term_claims,
    _src_pre_termination,
    _src_separations,
    _src_training,
    _topic_filter,
)
from .law import (  # noqa: F401
    _LAW_CACHE,
    _LAW_CACHE_MAX,
    _LAW_CACHE_TTL,
    _gather_case_law,
    _gather_law,
    _gather_law_cached,
)
from .gather import (  # noqa: F401
    _SOURCES,
    gather_evidence,
    resolve_matter_jurisdiction,
)
from .matters import (  # noqa: F401
    audit_matter,
    latest_memo,
    load_matter,
    load_messages,
)
from .chat import (  # noqa: F401
    _MATTER_TYPE_EXPECTED,
    _SYSTEM,
    _build_prompt,
    _corpus_text,
    _generate,
    _history_text,
    _intake_source_gaps,
    _intake_text,
    _scope_text,
    intake_gaps,
    run_chat_turn,
    validate_citations,
)
from .details import (  # noqa: F401
    _APPENDIX_SECTIONS,
    _AUDIT_ACTION_LABELS,
    _AUDIT_ROW_CAP,
    _accommodation_section,
    _alert_section,
    _compliance_section,
    _custody_table,
    _describe_audit,
    _detail_accommodation,
    _detail_alert,
    _detail_compliance,
    _detail_discipline,
    _detail_law,
    _detail_training,
    _discipline_audit_by_record,
    _discipline_section,
    _er_audit_by_case,
    _er_section,
    _group_audit,
    _hd,
    _incident_section,
    _law_section,
    _training_section,
)
from .packet import (  # noqa: F401
    _CHRONOLOGY_KINDS,
    _MEMO_CSS_EXTRA,
    _ZIP_DIRS,
    _build_zip,
    _case_file_html,
    _chronology_html,
    _chronology_rows,
    _cited_ids,
    _collect_source_files,
    _fetch_audit_log,
    _memo_html,
    _render_pdf,
    _research_html,
    _safe_detail,
    build_defense_packet,
    safe_name,
)
