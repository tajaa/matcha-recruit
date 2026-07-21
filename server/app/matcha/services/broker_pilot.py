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

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from app.core.services.genai_client import get_genai_client
from app.core.services.pdf import render_pdf

from .claims_readiness import _PDF_CSS, _esc, _fmt_dt
from .legal_defense import validate_citations, _parse_json  # pure, unit-tested

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"
_GEMINI_TIMEOUT = 90
_HISTORY_TURNS = 12
_DOC_TEXT_CAP = 12_000        # raw text per document fed to the model per turn
_MAX_DOC_TEXT_BLOCKS = 5      # most-recent docs whose raw text rides along
_STORED_TEXT_CAP = 40_000     # extracted_text cap at write time
_MAX_DOCS_PER_SESSION = 12
_MAX_KEY_FIGURES = 20
_MAX_NOTABLE = 10

# Structured answer buckets. A turn is a short lead answer plus three reviewable
# lists — the questions to put to the client, the strategic considerations, and
# the concrete gaps. The lists are DATA, not headings inside the prose: the
# console renders them as sections and the memo lays them out with footnote
# citations, neither of which can be done to a markdown blob.
_MAX_QUESTIONS = 6
_MAX_FINDINGS = 8             # per bucket (considerations, gaps)
_FINDING_POINT_CAP = 400
_QUESTION_CAP = 300
_GAP_SEVERITIES = ("high", "medium", "low")

DOC_TYPES = (
    "loss_run", "dec_page", "quote", "carrier_letter",
    "bordereau", "policy_form", "financials", "contract", "other",
)
_LINES = ("wc", "gl", "auto", "property", "package", "umbrella", "epl", "cyber", "other")

DISCLAIMER = (
    "Prepared from broker-uploaded documents and platform records to support "
    "broker analysis. Not coverage, legal, or actuarial advice. Verify all "
    "figures against actual policy forms and carrier documents before relying "
    "on them."
)


# --------------------------------------------------------------------------- #
# Starter templates ("modes")
# --------------------------------------------------------------------------- #
# A mode is a named starting point for a session. It carries a default `title`,
# tailored `starters` (surfaced in the console, pre-filled into the composer —
# never auto-sent), and a `focus` directive that is appended to the analyst
# system prompt on EVERY turn of the session (persisted via
# broker_pilot_sessions.template_key). The `focus` strings deliberately name the
# corpus cid namespaces (`platform:` / `clause:` / `doc:` / `docfig:` — see the
# module header) so the model grounds where the mode intends. Mirrors Legal
# Pilot's matter-type-keyed starters + Analysis Pilot's `_DOMAIN_LENSES`.
#
# A session with NO template_key keeps the generic behavior (the frontend falls
# back to its default starter list) — the catalog is additive.

PILOT_TEMPLATES: tuple[dict, ...] = (
    {
        "key": "contract_review",
        "label": "Client contract review",
        "description": "Check the client's contractual insurance and indemnity "
                       "requirements against the coverage they carry.",
        "title": "Contract review",
        "focus": (
            "Center the analysis on the "
            "client's contractual risk transfer: the extracted indemnity clauses "
            "(`clause:` records) and the coverage lines the client carries "
            "(`platform:limits.*`). Assess whether carried limits meet each "
            "contract's required limits, whether required endorsements "
            "(additional insured, waiver of subrogation, primary & "
            "non-contributory) appear to be in place, and the insurability of "
            "each indemnity form. A recorded clause verdict is a starting point "
            "for counsel — report it as such and never state that a clause is or "
            "is not enforceable. Insurance and risk-transfer terms only. The "
            "`jur:` records are the client's codified EMPLOYMENT-law obligations "
            "(final pay, leave, pay transparency, anti-discrimination) — cite "
            "them only where an employment-practices exposure is genuinely at "
            "issue; they do not speak to contractual insurance requirements, so "
            "never stretch one to cover a limits or endorsement question."
        ),
        "starters": [
            "Do the limits this client carries meet what their contracts require? Flag every gap.",
            "Which indemnity clauses create uninsurable or likely-void exposure, and why?",
            "Which contracts require endorsements (additional insured / waiver of subrogation / primary & non-contributory) the client may not carry?",
        ],
        "required_docs": (
            {
                "doc_type": "contract",
                "label": "Client contract",
                "hint": "The agreement whose insurance and indemnity requirements you want checked — "
                        "a customer contract, lease, MSA, or subcontract. On-platform clients: adding "
                        "it under the client's Contracts page gives full clause extraction and "
                        "insurability verdicts instead of a basic read.",
                "required": True,
                "platform_source": "clauses",
            },
            {
                "doc_type": "dec_page",
                "label": "Current dec page",
                "hint": "The limits the client actually carries today — what the contract's "
                        "requirements get measured against.",
                "required": False,
                "platform_source": "limits",
            },
        ),
    },
    {
        "key": "mid_year",
        "label": "Mid-year check-in",
        "description": "Mid-term review of loss activity and emerging exposures "
                       "since the policy bound.",
        "title": "Mid-year check-in",
        "focus": (
            "This is a mid-term account review. "
            "Center on what has CHANGED since the policy bound: recent loss "
            "development (`platform:lossdev.*`), open vs. closed claims, new "
            "safety or employee-relations activity (`incident:` / `er_case:` "
            "records), and exposure shifts (headcount, new locations, property, "
            "venue). Surface what the broker should raise with the client now "
            "rather than waiting for renewal."
        ),
        "starters": [
            "What has changed on this account since the policy bound that I should flag now?",
            "How is loss development trending mid-term — is anything developing adversely?",
            "Any new exposures — locations, headcount, contracts — that affect the current program?",
        ],
        "required_docs": (
            {
                "doc_type": "loss_run",
                "label": "Current loss run",
                "hint": "Mid-term loss activity. Satisfied automatically when the client already has "
                        "loss-development history on the platform.",
                "required": True,
                "platform_source": "lossdev",
            },
        ),
    },
    {
        "key": "renewal_90",
        "label": "90 days before renewal",
        "description": "Pre-renewal readiness: loss development, submission "
                       "completeness, and likely underwriter questions.",
        "title": "90-day renewal check-in",
        "focus": (
            "Renewal is roughly 90 days "
            "out. Center on renewal readiness: reserve and loss development with "
            "projected ultimates (`platform:lossdev.*`), submission-data "
            "completeness (`platform:readiness`), the controls story "
            "(`platform:controls`), and the workers'-comp / EPL metrics an "
            "underwriter will scrutinize (`platform:wc`, `platform:epl.*`), and "
            "the codified employment-law obligations that shape the EPL exposure "
            "(`jur:` records). End "
            "every analysis with the concrete data the broker should gather "
            "before marketing the account."
        ),
        "starters": [
            "Give me a pre-renewal read: reserve development, biggest exposures, and pricing pressure.",
            "What's missing from the submission data, and what will the underwriter ask for first?",
            "Summarize the controls and readiness story I can lead the renewal narrative with.",
        ],
        "required_docs": (
            {
                "doc_type": "loss_run",
                "label": "Valued loss run",
                "hint": "The loss run the market will price off. Satisfied automatically when the "
                        "client already has loss-development history on the platform.",
                "required": True,
                "platform_source": "lossdev",
            },
            {
                "doc_type": "dec_page",
                "label": "Expiring dec page",
                "hint": "The expiring terms the renewal gets compared against.",
                "required": False,
                "platform_source": "limits",
            },
        ),
    },
    {
        "key": "new_business",
        "label": "New business appetite read",
        "description": "Prospect appetite read for a new client from the "
                       "documents and data on file.",
        "title": "New business appetite read",
        "focus": (
            "This is a new-business / "
            "prospect evaluation. Center on how a carrier would view the account: "
            "the risk profile from available data (industry, headcount, venue, "
            "property), what the uploaded documents (loss runs, current dec "
            "pages) reveal (`doc:` / `docfig:`), and the account's strengths and "
            "red flags from a market's point of view. Be explicit about what is "
            "not yet known and would need to be obtained to market the account."
        ),
        "starters": [
            "From what's on file, how would a carrier view this prospect's appetite and risk quality?",
            "What are the strengths I can lead with, and the red flags I need to get ahead of?",
            "What information is missing to market this account, and what should I request first?",
        ],
        # Nothing hard-required: an appetite read is exactly the conversation a
        # broker has BEFORE the prospect hands over paper.
        "required_docs": (
            {
                "doc_type": "loss_run",
                "label": "Prior-carrier loss runs",
                "hint": "The single biggest driver of how a market views the account.",
                "required": False,
                "platform_source": "lossdev",
            },
            {
                "doc_type": "dec_page",
                "label": "Current dec page",
                "hint": "What the prospect carries today — the program you'd be competing against.",
                "required": False,
                "platform_source": "limits",
            },
        ),
    },
    {
        "key": "loss_run",
        "label": "Loss-run deep dive",
        "description": "Focused analysis of the uploaded loss runs — frequency, "
                       "severity, development, and large claims.",
        "title": "Loss-run deep dive",
        "focus": (
            "Center the analysis on the "
            "uploaded loss-run documents (`doc:` / `docfig:`) alongside the "
            "platform loss development on file (`platform:lossdev.*`). Break down "
            "frequency, severity, paid vs. reserved, open claims, and any large "
            "or adversely developing losses. Reconcile the uploaded loss runs "
            "against the platform loss data and call out any discrepancies "
            "explicitly, citing both sides."
        ),
        "starters": [
            "Break down the uploaded loss runs: frequency, severity, and any large or open claims.",
            "How do the uploaded loss runs reconcile with the platform loss development on file?",
            "Which claims are developing adversely, and what does that imply for the reserves?",
        ],
        # No `platform_source`, deliberately: this mode's whole point is the
        # claim-level carrier document. Platform loss triangles are aggregates —
        # they can't answer "which claims are developing adversely", so they must
        # NOT quietly satisfy the requirement the way they do for mid_year/renewal.
        "required_docs": (
            {
                "doc_type": "loss_run",
                "label": "Carrier loss run",
                "hint": "The claim-level document itself. Platform loss triangles don't substitute — "
                        "this mode reconciles the two against each other.",
                "required": True,
                "platform_source": None,
            },
        ),
    },
    {
        "key": "quote_comparison",
        "label": "Quote comparison",
        "description": "Compare competing quotes against each other and against "
                       "the loss history.",
        "title": "Quote comparison",
        "focus": (
            "The broker is comparing carrier "
            "quotes. Center on the uploaded quote documents (`doc:` / `docfig:`): "
            "premium, limits, retentions, and — critically — the coverage "
            "differences, sublimits, and exclusions between them. Test whether "
            "the pricing is supported by the loss history (`platform:lossdev.*` "
            "and uploaded loss runs). Flag any coverage a lower premium may be "
            "quietly buying away. All terms must be verified against actual "
            "policy forms."
        ),
        "starters": [
            "Compare the uploaded quotes side by side: premium, limits, retentions, and key exclusions.",
            "Is the quoted pricing supported by the loss history, or is a cheaper quote buying less coverage?",
            "What coverage differences or sublimits between these quotes should I flag to the client?",
        ],
        # One quote clears the gate — comparing a single quote against the expiring
        # program is a real comparison. `single_quote_note` tells the analyst it is
        # working from one, so it can't silently narrate a head-to-head that isn't there.
        "required_docs": (
            {
                "doc_type": "quote",
                "label": "Carrier quote",
                "hint": "Upload every quote you want compared. One quote works — it gets compared "
                        "against the expiring program — but the mode is at its best with two or more.",
                "required": True,
                "platform_source": None,
            },
            {
                "doc_type": "dec_page",
                "label": "Expiring dec page",
                "hint": "The incumbent's terms, so a cheaper quote's coverage cuts show up.",
                "required": False,
                "platform_source": "limits",
            },
        ),
    },
)

_TEMPLATE_BY_KEY: dict[str, dict] = {t["key"]: t for t in PILOT_TEMPLATES}


def _lookup_template(key: str | None) -> dict | None:
    """Single resolution point for a stored template_key. None for a blank key
    (open analysis / legacy rows); a truthy key that no longer resolves is a
    stranded session (catalog edit while sessions persist) — warn so it's
    observable rather than silently un-moded."""
    if not key:
        return None
    t = _TEMPLATE_BY_KEY.get(key)
    if t is None:
        logger.warning("broker_pilot: session references unknown template_key %r", key)
    return t


def _public_template(t: dict) -> dict:
    """Public projection (drops the internal `focus`). Copies `starters` and
    `required_docs` (per-row too) so a caller mutating the returned structures
    can't corrupt the module catalog.

    `required_docs` IS public: the frontend renders it as the mode's document
    chips, and `broker_pilot_requirements` computes satisfaction from it — so the
    same dict the picker shows is the one the gate keys on."""
    return {
        "key": t["key"], "label": t["label"], "description": t["description"],
        "title": t["title"], "starters": list(t["starters"]),
        "required_docs": [dict(r) for r in t.get("required_docs") or ()],
    }


def template_catalog() -> list[dict]:
    """Public catalog for the frontend picker (omits the internal `focus`
    directive). Order is the catalog's declared order."""
    return [_public_template(t) for t in PILOT_TEMPLATES]


def get_template(key: str | None) -> dict | None:
    """Public template shape (no `focus`) for a stored key, or None."""
    t = _lookup_template(key)
    return _public_template(t) if t else None


def _mode_focus(key: str | None) -> str:
    """The per-mode system-prompt directive for a stored key, or "" (no mode).
    The `SESSION MODE — <label>.` header is composed here so it can never drift
    from the template's own `label`."""
    t = _lookup_template(key)
    return f"SESSION MODE — {t['label']}. {t['focus']}" if t else ""


_client = None


def _genai():
    global _client
    if _client is None:
        _client = get_genai_client()
    return _client


def _hum(s) -> str:
    if not s:
        return ""
    return str(s).replace("_", " ").replace("-", " ").strip().title()


# --------------------------------------------------------------------------- #
# Document extraction — one Gemini pass at upload time (classify + summarize
# + pull the figures a broker would cite). Never raises.
# --------------------------------------------------------------------------- #

_EXTRACT_PROMPT = """You are a commercial P&C insurance analyst. Classify the attached document and extract its citable substance.

Return ONLY valid JSON, exactly this shape:
{"doc_type": "<one of: loss_run | dec_page | quote | carrier_letter | bordereau | policy_form | financials | contract | other>",
 "title": "<short document title, e.g. 'Travelers WC loss run valued 2026-03-31'>",
 "carrier": "<carrier/issuer name or null>",
 "line": "<one of: wc | gl | auto | property | package | umbrella | epl | cyber | other, or null>",
 "period_label": "<policy period / valuation label shown, or null>",
 "effective_date": "<YYYY-MM-DD if the document shows an effective/valuation date, else null>",
 "summary": "<neutral 2-4 sentence summary of what this document is and shows, max 600 chars>",
 "key_figures": [{"label": "<what the figure is>", "value": "<the figure as shown>", "context": "<where/what it applies to>"}],
 "notable": ["<red flags, exclusions, conditions, endorsements, or anomalies worth a broker's attention>"]}

Rules:
- Extract ONLY what the document actually shows. Never invent, estimate, or infer figures.
- key_figures: at most 20 — premiums, limits, retentions/deductibles, claim counts, paid/reserved totals, mods, rates. The numbers a broker would cite.
- notable: at most 10 short items.
- doc_type "contract": a client/vendor/lease/MSA/subcontract agreement carrying insurance requirements or an indemnification clause — NOT an insurance policy form (that is policy_form).
- If the document is unreadable or not an insurance-related document, use doc_type "other" and say so in the summary."""


def _coerce_extraction(payload: dict) -> dict:
    """Clamp the model's extraction into the stored schema. Pure."""
    if not isinstance(payload, dict):
        payload = {}
    doc_type = str(payload.get("doc_type") or "").strip().lower()
    if doc_type not in DOC_TYPES:
        doc_type = "other"
    line = str(payload.get("line") or "").strip().lower() or None
    if line is not None and line not in _LINES:
        line = None

    def _s(key: str, cap: int):
        v = payload.get(key)
        return str(v).strip()[:cap] if v else None

    raw_figures = payload.get("key_figures")
    if not isinstance(raw_figures, list):
        raw_figures = []
    raw_notable = payload.get("notable")
    if not isinstance(raw_notable, list):
        raw_notable = []
    figures = []
    for f in raw_figures[:_MAX_KEY_FIGURES]:
        if not isinstance(f, dict):
            continue
        label = str(f.get("label") or "").strip()[:80]
        value = str(f.get("value") or "").strip()[:60]
        if not (label and value):
            continue
        figures.append({
            "label": label, "value": value,
            "context": str(f.get("context") or "").strip()[:160],
        })
    notable = [
        str(n).strip()[:200] for n in raw_notable[:_MAX_NOTABLE]
        if n and str(n).strip()
    ]
    return {
        "doc_type": doc_type,
        "title": _s("title", 200),
        "carrier": _s("carrier", 120),
        "line": line,
        "period_label": _s("period_label", 60),
        "effective_date": _s("effective_date", 10),
        "summary": _s("summary", 600),
        "key_figures": figures,
        "notable": notable,
    }


async def extract_document(data: bytes | None, text: str | None, *, is_pdf: bool,
                           filename: str) -> dict:
    """One-shot classify+extract. Best-effort, never raises —
    returns ``{"extraction": {...}, "available": bool}``."""
    payload: dict = {}
    try:
        from google.genai import types
        if is_pdf and data:
            part = types.Part.from_bytes(data=data, mime_type="application/pdf")
            contents = [f"{_EXTRACT_PROMPT}\n\nFILENAME: {filename}", part]
        else:
            contents = (
                f"{_EXTRACT_PROMPT}\n\nFILENAME: {filename}\n\n"
                f"DOCUMENT TEXT:\n{(text or '')[:_STORED_TEXT_CAP]}"
            )
        resp = await asyncio.wait_for(
            _genai().aio.models.generate_content(
                model=MODEL, contents=contents,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            ),
            timeout=_GEMINI_TIMEOUT,
        )
        payload = _parse_json(getattr(resp, "text", "") or "")
        if not payload:
            logger.warning("broker_pilot: unparseable extraction reply for %s — %s",
                           filename, _why_empty(resp))
    except Exception as exc:  # noqa: BLE001 - degrade to text_only, never 500 the upload
        logger.warning("broker_pilot: document extraction failed for %s: %s", filename, exc)
        payload = {}
    # `available` means the model produced a usable classification — not merely
    # any JSON. A degenerate `{}` reply must land text_only, not "ready".
    available = bool(payload.get("doc_type") or payload.get("summary")
                     or payload.get("key_figures")) if isinstance(payload, dict) else False
    return {"extraction": _coerce_extraction(payload), "available": available}


# --------------------------------------------------------------------------- #
# Corpus build — platform context sections + uploaded documents, one flat
# index of {cid, ref, summary, when} records. Pure (no DB) — unit-tested.
# --------------------------------------------------------------------------- #

def _slug(s) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "x"


def _fmt_num(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return f"{f:,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(v)


def _clause_records(ctx: dict) -> list[dict]:
    """One `clause:<contract_id>` record per contract carrying an extracted
    indemnity, so the analyst can cite the clause itself (verbatim quote + page)
    rather than paraphrasing it.

    Its own corpus source, NOT a prefixed record inside `platform` — the memo's
    appendix builder dispatches on cid prefix, and an unrecognized prefix inside
    the platform bucket would fall through to the native branch and re-render
    every cited platform record as a duplicate table.
    """
    recs: list[dict] = []
    for c in ((ctx or {}).get("limits") or {}).get("contracts") or []:
        if not isinstance(c, dict):
            continue
        ind = c.get("indemnity") or {}
        clause = (c.get("risk_transfer") or {}).get("indemnity") or {}
        if not clause.get("present"):
            continue
        bits = [f"{str(clause.get('form') or 'unclassified').replace('_', ' ')} form"]
        if clause.get("covers_sole_negligence"):
            bits.append("reaches the counterparty's sole negligence")
        if clause.get("defense_obligation"):
            bits.append("includes a duty to defend")
        if ind.get("verdict"):
            bits.append(f"verdict: {str(ind['verdict']).replace('_', ' ')}")
        if ind.get("statute"):
            bits.append(f"under {ind['statute']}")
        if c.get("provisional"):
            bits.append("PROVISIONAL — extraction not yet confirmed by a reviewer")
        quote = clause.get("quote")
        if quote:
            page = f", p. {clause['page']}" if clause.get("page") else ""
            bits.append(f'clause text{page}: "{quote}"')
        recs.append({
            "cid": f"clause:{c.get('id')}",
            "ref": f"Indemnity clause — {c.get('name') or 'contract'}",
            "summary": (f"{c.get('name') or 'Contract'}"
                        + (f" (counterparty {c['counterparty']})" if c.get("counterparty") else "")
                        + f": {'; '.join(bits)}."),
            "when": "current",
        })
    return recs


# Named drivers itemized in the corpus. The fleet headline always counts every
# driver; this only bounds how many are named, so a 400-driver fleet can't crowd
# out the rest of the grounding.
_FLEET_DRIVER_CAP = 25


def _platform_records(ctx: dict) -> list[dict]:
    """Serialize a `_tenant_context` / `_external_context` dict into compact
    corpus records. Every accessor is guard-railed — a missing/empty section
    emits nothing (it was already `_safe()`-defaulted upstream)."""
    ctx = ctx or {}
    recs: list[dict] = []

    def add(cid: str, ref: str, summary: str, when: str = "current"):
        recs.append({"cid": cid, "ref": ref, "summary": summary, "when": when})

    # Profile
    bits = [b for b in (
        f"industry {ctx.get('industry')}" if ctx.get("industry") else None,
        f"headcount {ctx.get('headcount')}" if ctx.get("headcount") else None,
        f"primary state {ctx.get('state')}" if ctx.get("state") else None,
    ) if b]
    if ctx.get("name") or bits:
        add("platform:profile", "Client profile",
            f"{ctx.get('name') or 'Client'}: {', '.join(bits) or 'no profile details on file'}.")

    # Workers' comp
    wc = ctx.get("wc") or {}
    if any(wc.get(k) is not None for k in ("trir", "dart_rate", "current_emr", "recordable_cases")):
        parts = []
        if wc.get("trir") is not None:
            parts.append(f"TRIR {_fmt_num(wc['trir'])}")
        if wc.get("dart_rate") is not None:
            parts.append(f"DART {_fmt_num(wc['dart_rate'])}")
        if wc.get("current_emr") is not None:
            parts.append(f"EMR {_fmt_num(wc['current_emr'])}")
        if wc.get("recordable_cases") is not None:
            parts.append(f"{wc['recordable_cases']} recordable case(s)")
        if wc.get("lost_days") is not None:
            parts.append(f"{wc['lost_days']} lost day(s)")
        if wc.get("severity_band"):
            parts.append(f"severity band {_hum(wc['severity_band'])}")
        add("platform:wc", "Workers' comp metrics", "; ".join(parts) + ".")

    # EPL — headline + per-factor sub-records
    epl = ctx.get("epl") or {}
    if epl.get("score") is not None:
        add("platform:epl", "EPL readiness",
            f"EPL readiness score {epl['score']} (band {_hum(epl.get('band')) or '—'}).")
        for f in epl.get("factors") or []:
            key = f.get("key") or f.get("item_key")
            if not key:
                continue
            status = f.get("status") or ("met" if f.get("met") else f.get("value"))
            add(f"platform:epl.{key}", f"EPL factor — {_hum(key)}",
                f"{_hum(key)}: {_hum(status) or 'status unknown'}"
                + (f" ({f['note']})" if f.get("note") else "") + ".")

    # Controls (tenant only)
    controls = (ctx.get("controls") or {}).get("controls") or []
    if controls:
        verified = sum(1 for c in controls if (c.get("status") or "") == "verified")
        add("platform:controls", "Proof of controls",
            f"{len(controls)} risk control(s) compiled; {verified} verified by the company.")

    # Submission readiness (tenant only)
    readiness = ctx.get("readiness") or {}
    if readiness.get("score") is not None:
        missing = readiness.get("items") or readiness.get("missing") or []
        open_items = [i for i in missing if isinstance(i, dict) and not i.get("complete", i.get("done"))]
        add("platform:readiness", "Submission readiness",
            f"Underwriting-data completeness {readiness['score']}/100"
            f" (band {_hum(readiness.get('band')) or '—'})"
            + (f"; {len(open_items)} item(s) outstanding" if open_items else "") + ".")

    # Venue severity
    venue = ctx.get("venue") or {}
    locs = venue.get("locations") or []
    if locs:
        tiers = {str(l.get("tier") or "").strip() for l in locs if isinstance(l, dict) and l.get("tier")}
        add("platform:venue", "Venue severity",
            f"{len(locs)} location(s) venue-scored"
            + (f"; tiers on file: {', '.join(sorted(tiers))}" if tiers else "") + ".")

    # Limit adequacy — per-line sub-records. build_review emits each line as
    # {key, label, carried{...}|None, contract_required{...}|None, gap: str|None,
    #  endorsement_gaps: [...]} (limit_adequacy.py lines_out).
    limits = ctx.get("limits") or {}
    for ln in limits.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        line = ln.get("key")
        label = ln.get("label") or _hum(line)
        carried = ln.get("carried") or {}
        if not line or not (carried or ln.get("contract_required")):
            continue
        bits = []
        if carried.get("per_occurrence") is not None:
            bits.append(f"carried ${_fmt_num(carried['per_occurrence'])}/occ")
        if carried.get("aggregate") is not None:
            bits.append(f"${_fmt_num(carried['aggregate'])} agg")
        if carried.get("carrier"):
            bits.append(f"carrier {carried['carrier']}")
        if carried.get("expiry_date"):
            bits.append(f"expires {carried['expiry_date']}")
        req = ln.get("contract_required") or {}
        if isinstance(req, dict) and req.get("per_occurrence"):
            bits.append(f"contracts require ${_fmt_num(req['per_occurrence'])}/occ")
        if ln.get("gap"):
            bits.append(str(ln["gap"]))
        if ln.get("endorsement_gaps"):
            bits.append(f"{len(ln['endorsement_gaps'])} endorsement gap(s)")
        add(f"platform:limits.{_slug(line)}", f"Coverage line — {label}",
            f"{label}: {'; '.join(bits) or 'recorded, no figures on file'}.")

    # Exclusion gaps
    exclusions = (ctx.get("exclusions") or {}).get("exclusions") or []
    for i, ex in enumerate(exclusions):
        if not isinstance(ex, dict):
            continue
        name = ex.get("name") or ex.get("exclusion") or f"exclusion {i + 1}"
        add(f"platform:exclusions.{i}", f"Exclusion exposure — {_hum(name)}",
            f"{_hum(name)}: {ex.get('why') or ex.get('detail') or 'flagged for this industry/state'}.")

    # Loss development — per line+period sub-records. build_development emits
    # periods as {period_label, points: [{paid, reserved, incurred, claim_count,
    # open_count, ...}], latest_incurred, ultimate, adverse_development}
    # (loss_development.py build_triangle).
    lossdev = ctx.get("loss_development") or {}
    for ln in lossdev.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        line = ln.get("line") or "wc"
        for p in ln.get("periods") or []:
            if not isinstance(p, dict) or not p.get("period_label"):
                continue
            label = p["period_label"]
            latest = (p.get("points") or [{}])[-1]
            bits = []
            if latest.get("claim_count") is not None:
                bits.append(f"{latest['claim_count']} claim(s)")
            if latest.get("open_count") is not None:
                bits.append(f"{latest['open_count']} open")
            if latest.get("paid") is not None:
                bits.append(f"paid ${_fmt_num(latest['paid'])}")
            if p.get("latest_incurred") is not None:
                bits.append(f"incurred ${_fmt_num(p['latest_incurred'])}")
            if p.get("ultimate") is not None:
                bits.append(f"projected ultimate ${_fmt_num(p['ultimate'])}")
            add(f"platform:lossdev.{_slug(line)}.{_slug(label)}",
                f"Loss history — {_hum(line)} {label}",
                f"{_hum(line)} policy period {label}: {'; '.join(bits) or 'on file'}.",
                when=str(label))

    # Property
    prop = ctx.get("property") or {}
    rollup = prop.get("rollup") or prop if isinstance(prop, dict) else {}
    if isinstance(rollup, dict) and (rollup.get("building_count") or rollup.get("total_tiv")):
        bits = []
        if rollup.get("building_count"):
            bits.append(f"{rollup['building_count']} building(s)")
        if rollup.get("total_tiv"):
            bits.append(f"TIV ${_fmt_num(rollup['total_tiv'])}")
        if rollup.get("cope_grade") or rollup.get("worst_cope_grade"):
            bits.append(f"COPE grade {rollup.get('cope_grade') or rollup.get('worst_cope_grade')}")
        if rollup.get("insured_to_value_pct") is not None:
            bits.append(f"ITV {_fmt_num(rollup['insured_to_value_pct'])}%")
        add("platform:property", "Commercial property",
            f"Property on file: {'; '.join(bits)}.")

    # Property sub-structures — cat / exposure / plan / risk are computed by
    # `_tenant_context` alongside the rollup (submission.py) and were previously
    # dropped here, so the broker could read them in the packet PDF while the
    # chat could not cite them at all. Off-platform clients carry a flat
    # broker-entered snapshot under `property` with none of these keys, so every
    # guard below silently emits nothing for them (never a KeyError).
    prop = prop if isinstance(prop, dict) else {}
    cat = prop.get("cat")
    if isinstance(cat, dict) and cat.get("worst_tier"):
        bits = ["worst catastrophe tier " + _hum(cat["worst_tier"])
                + (f" ({_hum(cat['worst_peril'])})" if cat.get("worst_peril") else "")]
        if cat.get("buildings_total"):
            bits.append(f"{cat.get('severe_high_count') or 0} of {cat['buildings_total']}"
                        " building(s) at high or severe")
            if cat.get("buildings_geocoded") is not None:
                bits.append(f"{cat['buildings_geocoded']}/{cat['buildings_total']} geocoded")
        tiers = cat.get("by_peril")
        if isinstance(tiers, dict) and tiers:
            bits.append("tiers by peril: "
                        + ", ".join(f"{_hum(p)} {_hum(t)}" for p, t in sorted(tiers.items())))
        # A wind/wildfire tier is a directional baseline, not a hazard-agency
        # probability — say so, or it gets cited as if it were modeled.
        if cat.get("worst_peril_documented") is False:
            bits.append("the worst peril's tier is a directional baseline, "
                        "not a hazard-agency-documented probability")
        add("platform:property.cat", "Property catastrophe exposure", "; ".join(bits) + ".")

    exposure = prop.get("exposure")
    if isinstance(exposure, dict) and any(
            exposure.get(k) for k in ("total_aal", "worst_pml", "coinsurance_shortfall")):
        bits = []
        if exposure.get("total_aal"):
            bits.append(f"modeled AAL ${_fmt_num(exposure['total_aal'])}")
        if exposure.get("worst_pml"):
            bits.append(f"worst PML ${_fmt_num(exposure['worst_pml'])}"
                        + (f" ({_hum(exposure['worst_pml_peril'])})"
                           if exposure.get("worst_pml_peril") else ""))
        if exposure.get("coinsurance_shortfall"):
            bits.append(f"coinsurance shortfall ${_fmt_num(exposure['coinsurance_shortfall'])}")
        summary = "; ".join(bits) + "."
        if exposure.get("basis"):
            summary += f" Basis: {exposure['basis']}."
        add("platform:property.exposure", "Property modeled exposure", summary)

    plan = prop.get("plan")
    fixes = plan.get("fixes") if isinstance(plan, dict) else None
    # The cid keys on the fix's own key (+ its building), NOT its list position:
    # build_plan re-ranks by severity and $ impact on every corpus build, and the
    # corpus is rebuilt for each chat turn AND again at memo time. A positional
    # cid would silently point at a different fix once the ranking moved, and the
    # citation gate can't catch that — the id still resolves.
    plan_seen: dict[str, int] = {}
    for i, fx in enumerate(fixes or []):
        if not isinstance(fx, dict):
            continue
        label = fx.get("label") or _hum(fx.get("key")) or f"property fix {i + 1}"
        slug = _slug(fx.get("key") or label)
        if fx.get("building_id"):
            slug = f"{slug}.{_slug(fx['building_id'])}"
        n = plan_seen.get(slug, 0)
        plan_seen[slug] = n + 1
        if n:                      # same fix twice on one building — keep cids unique
            slug = f"{slug}-{n + 1}"
        bits = [f"severity {_hum(fx.get('severity')) or 'unrated'}"]
        if fx.get("impact"):
            bits.append(f"projected impact {fx['impact']}")
        if fx.get("detail"):
            bits.append(str(fx["detail"]))
        add(f"platform:property.plan.{slug}", f"Property fix — {label}",
            f"{label}: {'; '.join(bits)}.")

    prisk = prop.get("risk")
    if isinstance(prisk, dict) and prisk.get("score") is not None:
        bits = [f"TIV-weighted property risk score {prisk['score']}/100"]
        if prisk.get("grade"):
            bits.append(f"grade {prisk['grade']}")
        if prisk.get("risk_level"):
            bits.append(f"level {_hum(prisk['risk_level'])}")
        if prisk.get("rated") is not None:
            bits.append(f"{prisk['rated']} building(s) rated")
        top = next((t for t in (prisk.get("top_risks") or []) if isinstance(t, dict)), None)
        if top:
            bits.append(f"worst building {top.get('name') or 'unnamed'} at {top.get('score')}"
                        + (f" ({top['grade']})" if top.get("grade") else ""))
        add("platform:property.risk", "Property risk score", "; ".join(bits) + ".")

    # Fleet / driver risk — the commercial-auto input. Tenant only, and only
    # when the client owns `driver_risk` (`_tenant_context` gates the fetch).
    fleet = ctx.get("fleet") or {}
    fsum = fleet.get("summary") if isinstance(fleet, dict) else None
    if isinstance(fsum, dict) and fsum.get("total_drivers"):
        bits = [f"fleet grade {fsum.get('grade') or 'n/a'}",
                f"{fsum['total_drivers']} driver(s) on file",
                f"{fsum.get('clean', 0)} clean / {fsum.get('marginal', 0)} marginal / "
                f"{fsum.get('high_risk', 0)} high-risk"]
        if fsum.get("clean_pct") is not None:
            bits.append(f"{fsum['clean_pct']}% clean")
        if fsum.get("overdue_reviews"):
            bits.append(f"{fsum['overdue_reviews']} overdue MVR review(s)")
        add("platform:fleet", "Driver risk — fleet",
            "; ".join(bits) + ". Tiers are derived from employer-recorded MVR reviews, "
            "not a pulled motor-vehicle record — directional.")
        # Sub-records for the drivers that move an auto quote: high-risk first,
        # then marginal, capped. `build_fleet` already sorts worst-first. The cid
        # keys on the row id, not the list position, because the sort is by score
        # and re-runs on every corpus build (the `platform:property.plan.*`
        # lesson: a positional cid still resolves after a re-rank, just to a
        # different driver).
        rated = [d for d in (fleet.get("drivers") or [])
                 if isinstance(d, dict) and d.get("tier") in ("high_risk", "marginal")]
        if len(rated) > _FLEET_DRIVER_CAP:
            add("platform:fleet.truncated", "Driver risk — coverage note",
                f"{len(rated)} driver(s) are rated marginal or high-risk; the "
                f"{_FLEET_DRIVER_CAP} worst are itemized below. The fleet totals in "
                "`platform:fleet` count all of them.")
            rated = rated[:_FLEET_DRIVER_CAP]
        for d in rated:
            name = d.get("driver_name") or "Unnamed driver"
            dbits = [f"tier {_hum(d['tier'])}", f"severity score {d.get('score')}/100"]
            if d.get("license_status"):
                dbits.append(f"license {_hum(d['license_status'])}")
            if d.get("violation_count"):
                dbits.append(f"{d['violation_count']} moving violation(s)")
            if d.get("accident_count"):
                dbits.append(f"{d['accident_count']} accident(s)")
            if d.get("major_violation"):
                dbits.append("major violation (DUI/reckless)")
            if d.get("overdue"):
                dbits.append("MVR review overdue")
            add(f"platform:fleet.{_slug(d.get('id') or name)}", f"Driver — {name}",
                f"{name}: {'; '.join(dbits)}.",
                when=str(d.get("review_date") or "current"))

    # Composite risk index — headline + per-component sub-records, mirroring the
    # EPL block above. Tenant only: `_external_context` has no company row to
    # compute it from, so the key is simply absent for off-platform clients.
    risk = ctx.get("risk_index") or {}
    if isinstance(risk, dict) and risk.get("index") is not None:
        bits = [f"composite risk index {risk['index']}/100"]
        if risk.get("band"):
            bits.append(f"band {_hum(risk['band'])}")
        if risk.get("index_low") is not None and risk.get("index_high") is not None:
            bits.append(f"uncertainty band {risk['index_low']}–{risk['index_high']}")
        if risk.get("index_confidence"):
            bits.append(f"{_hum(risk['index_confidence'])} confidence")
        if risk.get("coverage") is not None:
            try:
                bits.append(f"{round(float(risk['coverage']) * 100)}% of component weight scored")
            except (TypeError, ValueError):
                pass
        missing = [m.get("label") or _hum(m.get("key"))
                   for m in (risk.get("components_missing") or []) if isinstance(m, dict)]
        if missing:
            bits.append("not scored: " + ", ".join(m for m in missing if m))
        add("platform:risk", "Composite risk index", "; ".join(bits) + ".")
        for c in risk.get("components") or []:
            if not isinstance(c, dict) or not c.get("key") or c.get("score") is None:
                continue
            label = c.get("label") or _hum(c["key"])
            cbits = [f"score {c['score']}/100", f"weight {c.get('weight')}"]
            if c.get("confidence"):
                cbits.append(f"{_hum(c['confidence'])} confidence")
            if c.get("detail"):
                cbits.append(str(c["detail"]))
            add(f"platform:risk.{_slug(c['key'])}", f"Risk index component — {label}",
                f"{label}: {'; '.join(cbits)}.")

    return recs


def _doc_records(docs: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """(doc records, docfig records, notes) for the corpus. `docs` are
    broker_pilot_documents rows (dicts; `extraction` may be a JSON string)."""
    doc_recs, fig_recs, notes = [], [], []
    for d in docs or []:
        status = d.get("status") or "processing"
        name = d.get("filename") or "document"
        if status == "failed":
            notes.append(f"Document '{name}' failed processing and is not in scope.")
            continue
        if status == "processing":
            notes.append(f"Document '{name}' is still processing and is not in scope.")
            continue
        ext = d.get("extraction")
        if isinstance(ext, str):
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}
        ext = ext or {}
        did = str(d.get("id"))
        when = ext.get("period_label") or ext.get("effective_date") or _fmt_dt(d.get("created_at"))
        if status == "text_only" or not ext.get("summary"):
            summary = (f"Uploaded document '{name}' (classification unavailable — "
                       "raw text included below).")
        else:
            bits = [ext["summary"]]
            if ext.get("carrier"):
                bits.append(f"Carrier: {ext['carrier']}.")
            if ext.get("notable"):
                bits.append("Notable: " + "; ".join(ext["notable"]) + ".")
            summary = " ".join(bits)
        doc_recs.append({
            "cid": f"doc:{did}",
            "ref": ext.get("title") or name,
            "summary": summary,
            "when": str(when or "—"),
        })
        for n, f in enumerate(ext.get("key_figures") or []):
            fig_recs.append({
                "cid": f"docfig:{did}.{n}",
                "ref": f"{ext.get('title') or name} — {f.get('label')}",
                "summary": f"{f.get('label')}: {f.get('value')}"
                           + (f" ({f['context']})" if f.get("context") else ""),
                "when": str(when or "—"),
            })
    return doc_recs, fig_recs, notes


# Native operational records are leaner than Legal Pilot's 100/source — this
# corpus also carries the analytics aggregates and uploaded documents.
_NATIVE_PER_SOURCE_CAP = 50


# Legal Pilot sources that must NOT reach a broker chat. `gather_native_sources`
# iterates `legal_defense._SOURCES` wholesale, so anything added there lands here
# by default — right for agency charges and the termination-lifecycle records
# (core EPL underwriting context, and brokers already see named discipline
# records), wrong for leave: who took FMLA is medical-adjacent and belongs to the
# legal-defense corpus only. The filter lives here, not in the `_SOURCES` tuple,
# because it is a broker-side policy and two call sites unpack that tuple as a
# 4-tuple.
_BROKER_EXCLUDED_SOURCES = {"leave"}


async def gather_native_sources(conn, company_id) -> dict:
    """The operational records the platform natively generates for an
    on-platform company — IR/OSHA incidents, ER cases, compliance, discipline,
    training, policy acks, accommodations — reusing Legal Pilot's per-subsystem
    gatherers (same record shape, whole-company scope, feature-gated).

    Returns ``{"sources": {key: {label, records}}, "notes": [...]}``.
    Best-effort at every level: a failed gatherer degrades to a note, a total
    failure returns empty — the chat still grounds on analytics + documents.
    """
    from app.core.feature_flags import merge_company_features
    from . import legal_defense as ldef  # lazy: heavy module, no cycle at import time

    sources: dict = {}
    notes: list[str] = []
    try:
        row = await conn.fetchrow(
            "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id
        )
        features = merge_company_features(row["enabled_features"], row["signup_source"]) if row else {}
        for key, label, fn, enabled in ldef._SOURCES:
            if key in _BROKER_EXCLUDED_SOURCES or not enabled(features):
                continue
            try:
                recs = await fn(conn, company_id, None, None, None, None)
            except Exception as e:  # noqa: BLE001 — isolation is the point
                logger.warning("broker_pilot: native source %s unavailable: %s", key, e)
                notes.append(f"{label}: unavailable")
                continue
            if not recs:
                continue
            if len(recs) > _NATIVE_PER_SOURCE_CAP:
                notes.append(f"{label}: showing {_NATIVE_PER_SOURCE_CAP} most recent of {len(recs)}")
                recs = recs[:_NATIVE_PER_SOURCE_CAP]
            sources[key] = {"label": label, "records": recs}
    except Exception:  # noqa: BLE001 - degrade to analytics-only grounding
        logger.exception("broker_pilot: native gather failed for company %s", company_id)
        return {"sources": {}, "notes": ["Platform operational records: unavailable"]}
    return {"sources": sources, "notes": notes}


def _jurisdiction_records(index: dict) -> list[dict]:
    """Reshape `er_compliance_grounding.build_jurisdiction_corpus`'s flat index
    (``jur:<id>`` → {cid, requirement_id, state, category, title, description,
    statute_citation, source_url}) into corpus records (`{cid, ref, summary,
    when}`), the same shape every other source uses.

    ``summary`` mirrors ER's own corpus line — ``(STATE — category) title:
    description Citation: x`` — because `_corpus_text` renders ONLY `summary`
    (`ref` reaches the memo appendix, never the prompt). Two consequences are
    load-bearing: the **state** must be in the summary or a multi-state client's
    federal and per-state rows are byte-identical to the model, which then
    attributes one state's rule to another; and the **description** must be
    there or the model has a real cid with no statement of what the law
    requires, so it supplies the rule from its own weights while citing a
    genuine ID — the one hallucination `validate_citations` cannot catch.

    ``source_url`` rides along for the appendix (extra keys flow through
    `build_corpus`'s `{**r}` into the index untouched).

    Pure. Empty index → []."""
    recs: list[dict] = []
    for rec in (index or {}).values():
        state = (rec.get("state") or "").strip().upper() or "—"
        category = (rec.get("category") or "").strip()
        title = (rec.get("title") or "Requirement").strip()
        desc = (rec.get("description") or "").strip()
        citation = (rec.get("statute_citation") or "").strip() or "uncited"
        body = f"{title}: {desc}" if desc else title
        recs.append({
            "cid": rec["cid"],
            "ref": f"{state} — {title}",
            "summary": f"({state} — {category}) {body} Citation: {citation}",
            "when": "current",
            "source_url": rec.get("source_url") or None,
        })
    return recs


def build_corpus(subject_name: str, ctx: dict, docs: list[dict], native: dict | None = None,
                 jurisdiction: list[dict] | None = None,
                 jurisdiction_truncated: bool = False) -> dict:
    """Assemble the grounding corpus: `{sources, index, notes}` — the same shape
    Legal Pilot's `gather_evidence` returns, so `validate_citations` and the
    memo renderer work unchanged.

    ``native`` is the platform-generated operational corpus from
    ``gather_native_sources`` (company subjects only); None for off-platform
    clients, which instead get a note naming what an on-platform client adds.

    ``jurisdiction`` is the codified statutory-obligation corpus (``jur:`` cids)
    from ``_jurisdiction_records`` (company subjects only); empty/None for
    off-platform clients. It flows into the flat index like every other source,
    so the shared ``validate_citations`` gates ``jur:`` cids automatically.
    """
    platform = _platform_records(ctx)
    clauses = _clause_records(ctx)
    doc_recs, fig_recs, notes = _doc_records(docs)
    sources = {
        "platform": {"label": "Platform data on file", "records": platform},
    }
    if clauses:
        sources["clauses"] = {"label": "Contract indemnity clauses", "records": clauses}
    if jurisdiction:
        sources["jurisdiction"] = {"label": "Codified compliance obligations", "records": jurisdiction}
    if native is not None:
        sources.update(native.get("sources") or {})
        notes.extend(native.get("notes") or [])
    sources["documents"] = {"label": "Uploaded documents", "records": doc_recs}
    sources["doc_figures"] = {"label": "Key figures extracted from documents", "records": fig_recs}
    if not platform:
        notes.append("No platform data on file for this client yet.")
    if native is not None and not jurisdiction:
        # On-platform client (native is the company-subject signal) whose
        # codified grounding came back empty — no work states resolved, the
        # catalog held nothing for them, or the lookup failed. Say so: `_SYSTEM`
        # tells the model `jur:` records are present for on-platform clients, so
        # without this the broker reads a confident analysis with no statutory
        # grounding and no indication any was expected.
        notes.append(
            "Codified statutory obligations (`jur:`) are unavailable for this client — "
            "no work states resolved, or no codified requirements on file for them. "
            "Employment-law points in this analysis are NOT grounded in the statute catalog."
        )
    if jurisdiction and jurisdiction_truncated:
        # The catalog held more than the corpus cap. Say so, or the obligations
        # that fell off the LIMIT read as obligations that do not exist.
        notes.append(
            f"Codified statutory obligations were truncated to the first {len(jurisdiction)} "
            "records — this client has more codified obligations than are grounded here."
        )
    if native is None:
        notes.append(
            "Off-platform client: only broker-entered records ground this analysis. "
            "On-platform clients add native operational history — incidents, ER cases, "
            "compliance, discipline, training, policy acknowledgments."
        )
    index: dict = {}
    for key, s in sources.items():
        for r in s["records"]:
            index[r["cid"]] = {**r, "source": key, "source_label": s["label"]}
    return {"sources": sources, "index": index, "notes": notes}


# --------------------------------------------------------------------------- #
# Grounded AI turn (analyst, not advisor)
# --------------------------------------------------------------------------- #

_SYSTEM = """You are a commercial P&C insurance analysis assistant working for a licensed insurance broker who is preparing analysis for a client. You ground EVERY statement in the EVIDENCE CORPUS below: the client's platform records (`platform:` IDs), the company's operational records generated natively on the platform (`incident:` / `er_case:` / `compliance_req:` / `compliance_alert:` / `discipline:` / `training:` / `policy_ack:` / `accommodation:` / `charge:` (agency charges — EEOC/NLRB/OSHA/state) / `preterm:` (pre-termination risk reviews) / `separation:` (separation agreements) / `ptclaim:` (post-termination claims) IDs — present only for on-platform clients), the indemnification clauses extracted from the client's contracts (`clause:` IDs), the codified state and federal statutory obligations the client must follow (`jur:` IDs — present only for on-platform clients), and the broker's uploaded documents (`doc:` / `docfig:` IDs).

HARD RULES:
- Cite ONLY the bracketed IDs that appear in the EVIDENCE CORPUS. NEVER invent a figure, carrier, date, limit, premium, or ID.
- When an uploaded document and the platform data disagree, say so explicitly and cite both sides — do not silently pick one.
- Where the corpus does not address a point, say so plainly and put it under open_questions — never speculate or fill gaps.
- You MAY compute simple derived figures (differences, ratios, loss ratios, year-over-year changes) from cited values — state the inputs and cite their IDs.
- You are an ANALYST, NOT AN ADVISOR: do not recommend buying or declining coverage, do not opine on legal duties, and note that quotes and forms must be verified against actual policy language.
- On `clause:` records: your remit is INSURANCE AND RISK TRANSFER ONLY. Discuss indemnity form, insurability, and the endorsements a clause requires — never opine on payment terms, termination, IP, or dispute resolution, and never state that a clause IS or IS NOT enforceable. A recorded verdict is a starting point for counsel, so report it as such and say so.
- A `clause:` record marked PROVISIONAL comes from an unconfirmed AI extraction — say that whenever you rely on it.
- On `jur:` records: these are the client's CODIFIED state and federal statutory obligations (e.g. final-pay timing, pay-transparency, anti-discrimination). Cite the statute when a point turns on the law, and never state a legal conclusion, opine on whether the client is compliant, or give legal advice — surface the obligation and route the judgment to counsel.
- On property and index records: `platform:property.cat` (catastrophe tiers), `platform:property.exposure` (modeled AAL/PML), `platform:property.plan.<n>` (ranked property fixes) and `platform:property.risk` (TIV-weighted score) are the platform's own property analytics, and `platform:risk` plus `platform:risk.<component>` are its composite risk index. These are the platform's models, not carrier output — cite them as the platform's figures, and where a record says a tier is a directional baseline rather than a documented probability, repeat that qualifier when you use it.
- On `platform:fleet` and `platform:fleet.<driver>` records: these are the commercial-auto driver-risk view, scored from MVR data the EMPLOYER recorded — not a pulled motor-vehicle record and not carrier output. Say that whenever you rely on them, and treat a named driver's tier as the platform's score, not a finding about that person.
- Raw document text (DOCUMENT TEXT blocks) belongs to its `doc:` ID — cite that ID when using it.

ANSWER SHAPE — a short lead answer, then three reviewable lists. The broker reads
the lists, not a wall of prose:
- assistant_text: the direct answer to what was asked, at most 120 words, plain
  prose. Lead with the conclusion. Do NOT write section headings, do NOT restate
  the lists below, and do NOT pad with caveats that belong in key_questions.
- key_questions: what the broker should put to the client, the underwriter, or
  counsel before acting — including anything the corpus does not establish and
  the data that would settle it. This is the broker's next-action list.
- considerations: the strategic reading — what the material means for how the
  account is positioned, marketed, or negotiated. Judgment, grounded in cited
  records wherever it rests on a fact. Never a recommendation to buy or decline
  coverage.
- gaps: the concrete, specific gaps the record supports — a limit below what a
  contract requires, a missing endorsement, an uninsurable indemnity form, an
  exclusion or sublimit, a coverage line carried nowhere, or a hole in the data
  needed to place the account. Every gap MUST cite the records that establish it
  and carry a severity of "high", "medium", or "low". An unsupported gap is a
  key_question, not a gap — do not manufacture gaps to fill the list.

Emit a list ONLY where the corpus supports entries; an empty list is correct and
expected. Every `point` is one sentence.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<direct answer, <=120 words, no headings>",
 "key_questions": ["<question the broker should ask / what to obtain to settle it>"],
 "considerations": [{"point": "<what this means for the account>", "cited_ids": ["<id>", ...]}],
 "gaps": [{"point": "<the specific gap>", "severity": "high|medium|low", "cited_ids": ["<id>", ...]}],
 "evidence_map": [{"point": "<a factual observation grounded in the corpus>", "cited_ids": ["<id>", ...]}]}"""


def _corpus_text(corpus: dict, docs: list[dict]) -> str:
    out = []
    for key, s in corpus.get("sources", {}).items():
        if not s["records"]:
            continue
        out.append(f"## {s['label']} ({key})")
        for r in s["records"]:
            out.append(f"- [{r['cid']}] ({r['when']}) {r['summary']}")

    # Raw text for the most recent usable docs — deeper than the extraction,
    # bounded so five 15MB uploads can't blow the prompt.
    usable = [d for d in (docs or []) if d.get("status") in ("ready", "text_only")
              and (d.get("extracted_text") or "").strip()]
    for d in usable[-_MAX_DOC_TEXT_BLOCKS:]:
        text = (d.get("extracted_text") or "").strip()
        clipped = text[:_DOC_TEXT_CAP]
        note = " …(truncated)" if len(text) > _DOC_TEXT_CAP else ""
        out.append(f"### DOCUMENT TEXT [doc:{d.get('id')}] {d.get('filename')}")
        out.append(clipped + note)
    return "\n".join(out) or "(no records or documents in scope)"


def _history_text(history: list[dict]) -> str:
    msgs = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-_HISTORY_TURNS:]
    return "\n".join(f"[{m['role']}] {m.get('content', '')}" for m in msgs) or "(no prior messages)"


def _scope_text(corpus: dict) -> str:
    """Corpus notes as a prompt block. An absent record is indistinguishable from
    a record that doesn't exist, so without this the model answers confidently
    from whatever else is in scope and never says "you haven't given me the loss
    run". The notes are the only channel that tells it what is MISSING."""
    notes = corpus.get("notes") or []
    if not notes:
        return ""
    listed = "\n".join(f"- {n}" for n in notes)
    return (
        "\nSCOPE NOTES (limits of what you were given — honor them; never invent "
        f"material to fill a gap they name):\n{listed}\n"
    )


def _build_prompt(session: dict, subject_name: str, history: list[dict],
                  corpus: dict, docs: list[dict], latest: str) -> str:
    kind = "on-platform Matcha client" if session.get("subject_kind") == "company" \
        else "off-platform client (broker-recorded data only)"
    focus = _mode_focus(session.get("template_key"))
    mode_block = f"\n{focus}\n" if focus else ""
    return f"""{_SYSTEM}
{mode_block}
CLIENT: {subject_name} — {kind}
SESSION: {session.get('title') or 'Analysis session'}

EVIDENCE CORPUS (the ONLY records you may cite):
{_corpus_text(corpus, docs)}
{_scope_text(corpus)}
CONVERSATION (oldest first):
{_history_text(history)}

LATEST BROKER MESSAGE:
{latest}
"""


def _coerce_findings(raw, *, with_severity: bool) -> list[dict]:
    """Clamp a model-emitted findings list into the stored shape. Pure.

    Shape is `{point, cited_ids}` (+ `severity` for gaps) — the same shape the
    citation gate consumes, so a coerced list can go straight to it."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:_MAX_FINDINGS]:
        if not isinstance(item, dict):
            continue
        point = str(item.get("point") or "").strip()[:_FINDING_POINT_CAP]
        if not point:
            continue
        cited = item.get("cited_ids")
        ids = [str(c) for c in cited if c] if isinstance(cited, list) else []
        finding = {"point": point, "cited_ids": ids}
        if with_severity:
            sev = str(item.get("severity") or "").strip().lower()
            # Unknown/absent severity is not an error — the gap still stands, it
            # just isn't ranked. Never guess a severity the model didn't give.
            finding["severity"] = sev if sev in _GAP_SEVERITIES else None
        out.append(finding)
    return out


def _coerce_turn(data) -> dict:
    """Clamp one model turn into the stored answer schema. Pure.

    `key_questions` falls back to the legacy `open_questions` key so a model
    (or a stored message) still speaking the old shape keeps working."""
    if not isinstance(data, dict):
        data = {}
    questions = data.get("key_questions")
    if not isinstance(questions, list) or not questions:
        questions = data.get("open_questions")
    if not isinstance(questions, list):
        questions = []
    return {
        "assistant_text": str(data.get("assistant_text") or "").strip(),
        "key_questions": [
            str(q).strip()[:_QUESTION_CAP] for q in questions[:_MAX_QUESTIONS]
            if q and str(q).strip()
        ],
        "considerations": _coerce_findings(data.get("considerations"), with_severity=False),
        "gaps": _coerce_findings(data.get("gaps"), with_severity=True),
        "evidence_map": data.get("evidence_map") or [],
    }


def _gate(items: list[dict], index: dict) -> tuple[list[dict], list[str]]:
    """Run the shared anti-hallucination gate over a findings list, preserving
    per-item keys it doesn't know about (`severity`).

    `validate_citations` returns only `{point, cited_ids}`, so gate item-by-item
    and re-attach the rest — a positional zip would misalign the moment the gate
    skips a non-dict item."""
    clean, dropped = [], []
    for item in items:
        [checked], drops = validate_citations([item], index)
        clean.append({**item, **checked})
        dropped.extend(drops)
    return clean, dropped


def _why_empty(resp) -> str:
    """One-line diagnosis of a reply that produced no usable turn.

    The empty-answer path used to be silent, so a broker hitting the "I couldn't
    produce an analysis" fallback left nothing behind to diagnose — the three
    causes (safety block, output-cap truncation, prose instead of JSON) are
    indistinguishable from the outside and want different fixes."""
    cand = (getattr(resp, "candidates", None) or [None])[0]
    reason = getattr(cand, "finish_reason", None)
    usage = getattr(resp, "usage_metadata", None)
    return (
        f"finish_reason={reason} "
        f"prompt_feedback={getattr(resp, 'prompt_feedback', None)} "
        f"candidates_tokens={getattr(usage, 'candidates_token_count', None)} "
        f"thoughts_tokens={getattr(usage, 'thoughts_token_count', None)}"
    )


async def _generate_once(prompt: str) -> tuple[dict, str]:
    """One generation. Returns (coerced turn, raw text).

    ``response_mime_type="application/json"`` is what every sibling pilot already
    passes (`analysis_pilot._gen_config`); without it the model is free to answer
    in prose or fenced markdown, `_parse_json` returns {}, and the whole turn
    degrades to the fallback string."""
    from google.genai import types
    resp = await asyncio.wait_for(
        _genai().aio.models.generate_content(
            model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        ),
        timeout=_GEMINI_TIMEOUT,
    )
    text = getattr(resp, "text", "") or ""
    turn = _coerce_turn(_parse_json(text))
    if not turn["assistant_text"]:
        logger.warning(
            "broker_pilot: empty turn from model — %s text_len=%d head=%r",
            _why_empty(resp), len(text), text[:400],
        )
    return turn, text


async def _generate(session: dict, subject_name: str, history: list[dict],
                    corpus: dict, docs: list[dict], latest: str) -> dict:
    """Generate one turn, retrying once on a wholly empty result.

    The retry is deliberately narrow: an empty `assistant_text` AND no buckets
    means nothing usable came back at all (a safety block, a truncated reply, or
    a parse failure), and those are transient often enough that one more attempt
    beats showing the broker a dead end. A turn with *any* content is kept as-is
    — re-rolling a real answer would be non-determinism the broker can't see."""
    prompt = _build_prompt(session, subject_name, history, corpus, docs, latest)
    turn, _ = await _generate_once(prompt)
    if not _is_empty_turn(turn):
        return turn
    logger.info("broker_pilot: empty first turn — retrying once")
    retried, _ = await _generate_once(prompt)
    return retried if not _is_empty_turn(retried) else turn


def _is_empty_turn(turn: dict) -> bool:
    """Nothing usable came back — no answer and no populated bucket."""
    return not turn.get("assistant_text") and not any(
        turn.get(k) for k in ("key_questions", "considerations", "gaps", "evidence_map")
    )


async def run_chat_turn(session: dict, subject_name: str, history: list[dict],
                        corpus: dict, docs: list[dict], latest: str):
    """Async generator of SSE-shaped dicts for one grounded chat turn. Yields a
    status tick, then a single validated ``result`` (the citation gate runs
    before anything reaches the broker — groundedness over token-streaming)."""
    yield {"type": "status", "message": "Analyzing the documents and platform data…"}
    try:
        result = await _generate(session, subject_name, history, corpus, docs, latest)
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "Analysis timed out — please try again."}
        return
    except Exception:
        logger.exception("broker_pilot: chat turn failed")
        yield {"type": "error", "message": "Analysis failed — please try again."}
        return

    index = corpus.get("index", {})
    dropped: list[str] = []

    clean_map, drops = validate_citations(result.get("evidence_map"), index)
    result["evidence_map"] = clean_map
    dropped.extend(drops)

    considerations, drops = _gate(result.get("considerations") or [], index)
    result["considerations"] = considerations
    dropped.extend(drops)

    gaps, drops = _gate(result.get("gaps") or [], index)
    dropped.extend(drops)
    # A gap is a claim ABOUT the record — if the gate stripped every record it
    # rested on, nothing grounds it, so it doesn't survive as a gap. The prompt
    # says an unsupported gap is a question; demote it rather than drop it, so
    # the broker still sees the thread to pull.
    result["gaps"] = [g for g in gaps if g["cited_ids"]]
    demoted = [g["point"] for g in gaps if not g["cited_ids"]]
    if demoted:
        result["key_questions"] = (result.get("key_questions") or []) + demoted
        logger.info("broker_pilot: demoted %d ungrounded gap(s) to key questions", len(demoted))

    if dropped:
        result["dropped_citations"] = dropped
        logger.info("broker_pilot: dropped %d hallucinated citation(s)", len(dropped))
    if not result["assistant_text"]:
        # Nothing usable survived (or ever arrived). Surface it as an ERROR, not a
        # result: an error is transient in the console and — unlike a result — is
        # never persisted, so a dead turn can't enter the history that grounds the
        # next one. `_generate` has already retried once and logged the cause.
        if _is_empty_turn(result):
            yield {"type": "error", "message": (
                "I couldn't produce an analysis from the material this time. "
                "Try rephrasing, or check that the documents finished processing."
            )}
            return
        # A turn with lists but no lead answer is still worth keeping — the
        # broker reads the lists. Say the lead is missing rather than fake one.
        result["assistant_text"] = (
            "No summary came back for this turn — the findings below are what the "
            "material supports."
        )
    yield {"type": "result", "data": result}


# --------------------------------------------------------------------------- #
# Memo PDF — analysis narrative + grounded observations with footnote-style
# citations + deterministic appendix (document extractions + platform sections
# rendered from the re-gathered context, never from model text).
# --------------------------------------------------------------------------- #

def _cited_ids(memo: dict) -> list[str]:
    """Every record cited anywhere in the turn, in footnote order.

    Spans ALL cited buckets — a record cited only by a gap still has to reach the
    evidence index and the appendix, or the memo would footnote it as [?] and
    omit the record it rests on."""
    seen, out = set(), []
    for bucket in ("evidence_map", "gaps", "considerations"):
        for item in memo.get(bucket) or []:
            for c in item.get("cited_ids") or []:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
    return out


_MEMO_CSS_EXTRA = """
  @page {
    size: Letter; margin: 20mm 16mm 18mm 16mm;
    @bottom-left { content: "Broker Pilot analysis memo — confidential; prepared for broker use";
      font-size: 7px; color: #9ca3af; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages);
      font-size: 7px; color: #9ca3af; }
  }
  body { padding: 0; }
  .letterhead { display:flex; justify-content:space-between; align-items:flex-end;
    border-bottom:2px solid #166534; padding-bottom:10px; margin-bottom:0; }
  .letterhead .company { font-size:13px; font-weight:600; color:#1a1a2e; }
  .letterhead .meta { font-size:9px; color:#888; text-align:right; line-height:1.5; }
  .brand { font-size:8px; letter-spacing:2px; text-transform:uppercase; color:#166534;
    font-weight:700; margin-bottom:2px; }
  h1 { border:none; color:#14532d; font-size:19px; }
  h2 { border-bottom:2px solid #166534; color:#14532d; page-break-after: avoid; }
  .prep { display:flex; gap:0; border:1px solid #e5e7eb; border-radius:8px;
    margin:12px 0 4px; overflow:hidden; }
  .prep > div { flex:1; padding:7px 12px; border-left:1px solid #e5e7eb; }
  .prep > div:first-child { border-left:none; }
  .prep .l { font-size:7.5px; text-transform:uppercase; letter-spacing:.8px; color:#888; }
  .prep .v { font-size:10.5px; font-weight:600; margin-top:2px; color:#1a1a2e; }
  .narr { background:#f4faf6; border-left:3px solid #166534; white-space:normal; }
  .narr p { margin:0 0 7px; } .narr p:last-child { margin-bottom:0; }
  tr, .cell, .obs { page-break-inside: avoid; }
  .appendix-section { page-break-before: always; }
  sup.cite { color:#166534; font-weight:700; }
  .obs { display:flex; gap:10px; margin:8px 0; padding:8px 10px;
    border:1px solid #e5e7eb; border-radius:8px; }
  .obs-n { flex-shrink:0; width:18px; height:18px; border-radius:50%;
    background:#166534; color:#fff; font-size:9px; font-weight:700;
    display:flex; align-items:center; justify-content:center; }
  .obs-point { font-weight:600; margin-bottom:2px; }
  .obs ul { margin:2px 0 0; }
  .sev { margin-left:6px; padding:1px 5px; border-radius:8px; font-size:7.5px;
    font-weight:700; text-transform:uppercase; letter-spacing:.6px; vertical-align:middle; }
  .sev-high { background:#fee2e2; color:#991b1b; }
  .sev-medium { background:#fef3c7; color:#92400e; }
  .sev-low { background:#e5e7eb; color:#4b5563; }
"""

_GONE = "(no longer in scope at generation time)"


def _doc_appendix_html(doc: dict) -> str:
    """Deterministic per-document appendix section rendered ONLY from the
    stored row + extraction (never model text)."""
    ext = doc.get("extraction")
    if isinstance(ext, str):
        try:
            ext = json.loads(ext)
        except Exception:
            ext = {}
    ext = ext or {}
    figures = "".join(
        f"<tr><td>{_esc(f.get('label'))}</td><td>{_esc(f.get('value'))}</td>"
        f"<td>{_esc(f.get('context'))}</td></tr>"
        for f in ext.get("key_figures") or []
    ) or "<tr><td colspan='3'>No figures extracted.</td></tr>"
    notable = "".join(f"<li>{_esc(n)}</li>" for n in ext.get("notable") or [])
    notable_block = f"<h3>Notable items</h3><ul>{notable}</ul>" if notable else ""
    size = doc.get("file_size")
    size_s = f"{round(size / 1024)} KB" if size else "—"
    return f"""
      <h2>Appendix — Document: {_esc(doc.get('filename'))}</h2>
      <div class="grid">
        <div class="cell"><div class="l">Type</div><div class="v">{_esc(_hum(doc.get('doc_type')) or 'Unclassified')}</div></div>
        <div class="cell"><div class="l">Carrier</div><div class="v">{_esc(ext.get('carrier')) if ext.get('carrier') else '—'}</div></div>
        <div class="cell"><div class="l">Period</div><div class="v">{_esc(ext.get('period_label')) if ext.get('period_label') else '—'}</div></div>
        <div class="cell"><div class="l">Uploaded</div><div class="v">{_fmt_dt(doc.get('created_at'))} · {size_s}{f" · {doc['page_count']} pp" if doc.get('page_count') else ''}</div></div>
      </div>
      <div class="narr">{_esc(ext.get('summary')) if ext.get('summary') else 'No AI summary available (raw text only).'}</div>
      <h3>Extracted key figures</h3>
      <table><thead><tr><th>Figure</th><th>Value</th><th>Context</th></tr></thead>
      <tbody>{figures}</tbody></table>
      {notable_block}
    """


def _platform_appendix_html(section: str, corpus: dict) -> str:
    """Deterministic appendix for a cited platform section: re-renders that
    section's corpus records (which were themselves minted from the re-gathered
    context) as a table."""
    recs = [r for r in (corpus.get("sources", {}).get("platform", {}).get("records") or [])
            if r["cid"] == f"platform:{section}" or r["cid"].startswith(f"platform:{section}.")]
    rows = "".join(
        f"<tr><td>{_esc(r.get('ref'))}</td><td>{_esc(r.get('summary'))}</td>"
        f"<td>{_esc(r.get('when'))}</td></tr>"
        for r in recs
    ) or f"<tr><td colspan='3'>{_GONE}</td></tr>"
    return f"""
      <h2>Appendix — Platform data: {_esc(_hum(section))}</h2>
      <table><thead><tr><th>Item</th><th>What the platform shows</th><th>As of</th></tr></thead>
      <tbody>{rows}</tbody></table>
    """


def _native_appendix_html(source_key: str, cited: list[str], corpus: dict) -> str:
    """Deterministic appendix for a cited native operational source (incidents,
    ER cases, discipline, …): re-renders that source's CITED records as a table."""
    src = corpus.get("sources", {}).get(source_key, {})
    cited_set = set(cited)
    recs = [r for r in (src.get("records") or []) if r["cid"] in cited_set]
    rows = "".join(
        f"<tr><td>{_esc(r.get('ref'))}</td><td>{_esc(r.get('summary'))}</td>"
        f"<td>{_esc(r.get('when'))}</td></tr>"
        for r in recs
    ) or f"<tr><td colspan='3'>{_GONE}</td></tr>"
    return f"""
      <h2>Appendix — Platform records: {_esc(src.get('label') or _hum(source_key))}</h2>
      <table><thead><tr><th>Ref</th><th>What the platform recorded</th><th>When</th></tr></thead>
      <tbody>{rows}</tbody></table>
    """


def _jurisdiction_appendix_html(cited: list[str], corpus: dict) -> str:
    """Deterministic appendix for cited codified obligations. Its own builder,
    NOT the native one: these are statutes, not records the platform generated
    about this client, and `_native_appendix_html` would head the table
    "Platform records" / "What the platform recorded" — misrepresenting
    provenance in the one artifact that leaves the building. Carries the
    citation and, where the catalog has it, a link to the source."""
    src = corpus.get("sources", {}).get("jurisdiction", {})
    cited_set = set(cited)
    recs = [r for r in (src.get("records") or []) if r["cid"] in cited_set]
    rows = "".join(
        f"<tr><td>{_esc(r.get('ref'))}</td><td>{_esc(r.get('summary'))}</td>"
        f"<td>{_link_or_dash(r.get('source_url'))}</td></tr>"
        for r in recs
    ) or f"<tr><td colspan='3'>{_GONE}</td></tr>"
    return f"""
      <h2>Appendix — Codified statutory obligations</h2>
      <p style="font-size:9px; color:#888;">Codified law on file for this client's
      jurisdictions, not legal advice. Verify against the source before relying on it.</p>
      <table><thead><tr><th>Obligation</th><th>What the law requires</th><th>Source</th></tr></thead>
      <tbody>{rows}</tbody></table>
    """


def _link_or_dash(url: str | None) -> str:
    """Escaped anchor for a catalog source_url, else an em dash. Only http(s) —
    the URL is catalog data rendered into a PDF, never a caller-supplied scheme."""
    u = (url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        return "—"
    return f'<a href="{_esc(u)}">{_esc(u)}</a>'


def _narrative_html(text: str) -> str:
    """Model narrative → escaped paragraphs (blank-line separated). Keeps the
    memo typographically clean without trusting model markup."""
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    if not paras:
        return "<p>—</p>"
    return "".join(f"<p>{_esc(p)}</p>" for p in paras)


def _memo_html(session: dict, subject_name: str, corpus: dict, memo: dict,
               docs: list[dict], broker_name: str | None = None) -> str:
    index = corpus.get("index", {})
    cited = _cited_ids(memo)
    fn = {c: i + 1 for i, c in enumerate(cited)}

    narrative = _narrative_html(memo.get("assistant_text") or "")

    def _findings_html(bucket: str, empty: str, *, severity: bool = False) -> str:
        out = ""
        for n, item in enumerate(memo.get(bucket) or [], start=1):
            cites = "".join(
                f"<li><sup class='cite'>[{fn.get(c, '?')}]</sup> "
                f"{_esc(index[c].get('summary', '')) if c in index else _GONE} "
                f"<span style='color:#888'>({_esc(index.get(c, {}).get('when', ''))})</span></li>"
                for c in (item.get("cited_ids") or [])
            )
            sev = str(item.get("severity") or "") if severity else ""
            chip = (f"<span class='sev sev-{_esc(sev)}'>{_esc(sev)}</span>"
                    if sev in _GAP_SEVERITIES else "")
            out += (f"<div class='obs'><div class='obs-n'>{n}</div>"
                    f"<div class='obs-body'><div class='obs-point'>{_esc(item.get('point'))}{chip}</div>"
                    f"<ul>{cites or '<li>—</li>'}</ul></div></div>")
        return out or f"<p>{empty}</p>"

    # Gaps lead — they are what the broker acts on. Severity orders them; an
    # unranked gap sorts last rather than being dropped from the memo.
    gaps = sorted(memo.get("gaps") or [],
                  key=lambda g: _GAP_SEVERITIES.index(g["severity"])
                  if g.get("severity") in _GAP_SEVERITIES else len(_GAP_SEVERITIES))
    memo = {**memo, "gaps": gaps}

    gaps_block = _findings_html("gaps", "No gaps were established by the record.", severity=True)
    cons_block = _findings_html("considerations", "None recorded.")
    points = _findings_html("evidence_map", "No grounded observations were recorded.")

    kq = "".join(f"<li>{_esc(q)}</li>" for q in (memo.get("key_questions") or []))
    kq_block = f"<ul>{kq}</ul>" if kq else "<p>None recorded.</p>"

    idx_rows = "".join(
        f"<tr><td>[{fn[c]}]</td><td>{_esc(index[c].get('source_label', ''))}</td>"
        f"<td>{_esc(index[c].get('ref', ''))}</td>"
        f"<td>{_esc(index[c].get('summary', ''))}</td>"
        f"<td>{_esc(index[c].get('when', ''))}</td></tr>"
        if c in index else
        f"<tr><td>[{fn[c]}]</td><td colspan='4'>{_GONE}</td></tr>"
        for c in cited
    ) or "<tr><td colspan='5'>No records cited.</td></tr>"

    # Appendix: every cited document (full extraction table) + every cited
    # platform section, each deterministic. docfig cites collapse into their
    # parent document's section, rendered once.
    docs_by_id = {str(d.get("id")): d for d in docs or []}
    appendix = ""
    seen_docs: set = set()
    seen_sections: set = set()
    seen_native: set = set()
    for c in cited:
        if c.startswith("doc:") or c.startswith("docfig:"):
            did = c.split(":", 1)[1].split(".", 1)[0]
            if did in seen_docs:
                continue
            seen_docs.add(did)
            doc = docs_by_id.get(did)
            if doc:
                appendix += f"<div class='appendix-section'>{_doc_appendix_html(doc)}</div>"
        elif c.startswith("platform:"):
            section = c.split(":", 1)[1].split(".", 1)[0]
            if section in seen_sections:
                continue
            seen_sections.add(section)
            appendix += f"<div class='appendix-section'>{_platform_appendix_html(section, corpus)}</div>"
        elif c.startswith("jur:"):
            # Statutes get their own appendix — see _jurisdiction_appendix_html.
            if "jurisdiction" in seen_native:
                continue
            seen_native.add("jurisdiction")
            appendix += f"<div class='appendix-section'>{_jurisdiction_appendix_html(cited, corpus)}</div>"
        else:
            # native operational record (incident:, er_case:, discipline:, …) —
            # one appendix table per source, listing the cited records.
            source_key = index.get(c, {}).get("source")
            if not source_key or source_key in seen_native:
                continue
            seen_native.add(source_key)
            appendix += f"<div class='appendix-section'>{_native_appendix_html(source_key, cited, corpus)}</div>"

    notes = "".join(f"<li>{_esc(n)}</li>" for n in corpus.get("notes") or [])
    notes_block = f"<h2>Scope notes</h2><ul>{notes}</ul>" if notes else ""

    doc_rows = "".join(
        f"<tr><td>{_esc(d.get('filename'))}</td><td>{_esc(_hum(d.get('doc_type')) or '—')}</td>"
        f"<td>{_esc(_hum(d.get('status')))}</td><td>{_fmt_dt(d.get('created_at'))}</td></tr>"
        for d in docs or []
    ) or "<tr><td colspan='4'>No documents uploaded.</td></tr>"

    kind_label = "On-platform Matcha client" if session.get("subject_kind") == "company" \
        else "Off-platform client (broker-recorded data)"
    mode = _lookup_template(session.get("template_key"))
    mode_cell = (f"<div><div class='l'>Mode</div><div class='v'>{_esc(mode['label'])}</div></div>"
                 if mode else "")
    generated = datetime.now(timezone.utc).strftime("%B %d, %Y · %H:%M UTC")
    record_total = sum(len(s.get("records") or []) for s in corpus.get("sources", {}).values())

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
      <style>{_PDF_CSS}{_MEMO_CSS_EXTRA}</style></head><body>
      <div class="letterhead">
        <div>
          <div class="brand">Matcha · Broker Pilot</div>
          <h1>Client Risk Analysis Memo</h1>
          <p class="sub">{_esc(session.get('title'))}</p>
        </div>
        <div class="meta">
          {f"<div class='company'>{_esc(broker_name)}</div>" if broker_name else ""}
          <div>Generated {generated}</div>
        </div>
      </div>

      <div class="prep">
        <div><div class="l">Client</div><div class="v">{_esc(subject_name)}</div></div>
        {mode_cell}
        <div><div class="l">Data basis</div><div class="v">{kind_label}</div></div>
        <div><div class="l">Records in scope</div><div class="v">{record_total}</div></div>
        <div><div class="l">Documents</div><div class="v">{len(docs or [])}</div></div>
        {f"<div><div class='l'>Prepared by</div><div class='v'>{_esc(broker_name)}</div></div>" if broker_name else ""}
      </div>

      <div class="narr"><b>About this memo.</b> A sourced analysis of this client's risk material — the broker's uploaded carrier documents combined with the client's platform records{", including the operational history generated on Matcha (incidents, ER cases, compliance, discipline, training)" if session.get('subject_kind') == 'company' else ""}. Every observation cites its underlying record; the evidence index and appendices reproduce the cited records verbatim. {_esc(DISCLAIMER)}</div>

      <h2>Analysis narrative</h2>
      <div class="narr">{narrative}</div>

      <h2>Key questions</h2>
      {kq_block}

      <h2>Strategic considerations</h2>
      {cons_block}

      <h2>Gaps identified in the record</h2>
      {gaps_block}

      <h2>Observations grounded in the material</h2>
      {points}

      <h2>Evidence index (cited records)</h2>
      <table><thead><tr><th>#</th><th>Source</th><th>Ref</th><th>Record</th><th>When</th></tr></thead>
      <tbody>{idx_rows}</tbody></table>

      <h2>Documents in this session</h2>
      <table><thead><tr><th>File</th><th>Type</th><th>Status</th><th>Uploaded</th></tr></thead>
      <tbody>{doc_rows}</tbody></table>

      {notes_block}
      {appendix}

      <div class="foot">{_esc(DISCLAIMER)}</div>
    </body></html>"""


async def _render_pdf(html_str: str) -> bytes:
    def _r() -> bytes:
        return render_pdf(html_str)
    return await asyncio.to_thread(_r)


async def build_memo_pdf(session: dict, subject_name: str, corpus: dict, memo: dict,
                         docs: list[dict], broker_name: str | None = None) -> dict:
    """Render the analysis memo. Returns ``{"pdf": bytes, "citations": [...]}``."""
    html = _memo_html(session, subject_name, corpus, memo, docs, broker_name=broker_name)
    pdf = await _render_pdf(html)
    return {"pdf": pdf, "citations": _cited_ids(memo)}
