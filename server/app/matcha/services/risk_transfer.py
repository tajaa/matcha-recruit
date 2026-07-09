"""Contract risk-transfer review — indemnity insurability verdicts (phase 1 of
broker contract review, layered on ``limit_adequacy``).

A P&C broker reviewing a contract before their client signs it asks two
questions the limit diff can't answer:

1. **Is the indemnity clause enforceable?** Most states have an anti-indemnity
   statute voiding some or all of an indemnity that shifts the indemnitee's own
   negligence onto the indemnitor.
2. **Is it insurable?** A broad-form indemnity covering the counterparty's
   *sole* negligence falls outside the CGL "insured contract" definition — the
   client would be personally on the hook for a promise their policy won't fund.

This module answers both deterministically, from a human-confirmed extraction.
The AI never rules — it only extracts the clause (``contract_parser``); the
verdict comes from ``_STATE_ANTI_INDEMNITY`` + the pure functions here.

Three invariants keep this honest:

* **Confirm-before-verdict.** An unconfirmed extraction yields
  ``provisional=True``; the UI and PDF label the verdict accordingly. Mirrors
  Analysis Pilot's ``needs_review`` gate.
* **Unmapped degrades to ``review``.** A state we can't cite a statute for
  never produces a confident verdict. Silence is not "no statute".
* **Project state controls construction.** Construction anti-indemnity statutes
  are typically *anti-waiver* — they attach to where the work is performed
  regardless of the contract's chosen law. Honoring only ``governing_state``
  would let a choice-of-law clause paper over a void indemnity.

Scope guard: this module reasons about **insurance and risk-transfer
provisions only**. It never opines on payment terms, termination, IP, or
dispute resolution — the same lane a broker stays in. Every rendered surface
carries ``DISCLAIMER``.
"""

import asyncio
import json
import logging
from typing import Optional, get_args

from fastapi import HTTPException, UploadFile

from app.config import get_settings
from app.core.services.pdf import safe_url_fetcher
from app.core.services.storage import get_storage
from app.matcha.models import limit_adequacy as _models

from . import contract_parser
from . import limit_adequacy as la

logger = logging.getLogger(__name__)

MAX_CONTRACT_BYTES = 15_000_000

_CONTRACT_COLS = """id, name, counterparty, status, requirements, ai_available, source_filename,
                    contract_type, governing_state, project_state, storage_path, risk_transfer,
                    confirmed_at, created_at, updated_at"""


DISCLAIMER = la.DISCLAIMER

# Derived from the Pydantic Literals so the API's accepted vocabulary and the
# extractor's whitelist can never drift — adding a value in one place is enough.
#
# Broad   — indemnitee covered even for its OWN SOLE negligence.
# Intermediate — indemnitee covered for its own PARTIAL/concurrent negligence.
# Limited — indemnitor covers only its own negligence. Always insurable.
CONTRACT_TYPES = list(get_args(_models.ContractType))
INDEMNITY_FORMS = list(get_args(_models.IndemnityForm))
INDEMNITY_DIRECTIONS = list(get_args(_models.IndemnityDirection))


# --- state anti-indemnity table --------------------------------------------
#
# ⚠️  PARTIAL TABLE — deliberately incomplete. Each row was individually cited;
# states we have not yet sourced are ABSENT, and an absent state degrades to the
# ``review`` verdict (never to "no statute"). Do NOT add rows by inference from
# neighboring states or from memory — anti-indemnity statutes vary in ways that
# don't follow regional patterns, and a wrong row silently produces a confident
# wrong verdict in an attorney-adjacent deliverable.
#
# To extend: consult a current 50-state survey (e.g. Saxe Doernberger & Vita's
# "Construction Anti-Indemnity Statutes", Matthiesen Wickert & Lehrer's
# "Anti-Indemnity Statutes in All 50 States") and add one row per state with its
# real citation. `_STATE_ANTI_INDEMNITY_COVERAGE` in the tests guards the shape.
#
# rule:
#   "own_negligence_void"  — indemnity for ANY of the indemnitee's own
#                            negligence is void; only LIMITED form survives.
#   "sole_negligence_void" — indemnity for the indemnitee's SOLE negligence is
#                            void; INTERMEDIATE form survives.
#   "none"                 — no construction anti-indemnity statute on point.
#
# Only the ``construction`` context is modeled today. Lease/vendor/MSA
# indemnities are governed by a different (and thinner) body of statutes, so
# those contract types fall through to the insurability analysis alone.

_STATE_ANTI_INDEMNITY: dict[str, dict] = {
    "CA": {"rule": "sole_negligence_void", "statute": "Cal. Civ. Code § 2782"},
    "NY": {"rule": "own_negligence_void", "statute": "N.Y. Gen. Oblig. Law § 5-322.1"},
    "TX": {"rule": "own_negligence_void", "statute": "Tex. Ins. Code §§ 151.101–.102"},
    "IL": {"rule": "own_negligence_void", "statute": "740 ILCS 35/1"},
    "GA": {"rule": "sole_negligence_void", "statute": "O.C.G.A. § 13-8-2(b)"},
    "WA": {"rule": "sole_negligence_void", "statute": "Wash. Rev. Code § 4.24.115"},
    "OH": {"rule": "own_negligence_void", "statute": "Ohio Rev. Code § 2305.31"},
    "MA": {"rule": "own_negligence_void", "statute": "Mass. Gen. Laws ch. 149 § 29C"},
    "OR": {"rule": "own_negligence_void", "statute": "Or. Rev. Stat. § 30.140"},
    "MN": {"rule": "own_negligence_void", "statute": "Minn. Stat. § 337.02"},
    "NC": {"rule": "own_negligence_void", "statute": "N.C. Gen. Stat. § 22B-1"},
    "VA": {"rule": "own_negligence_void", "statute": "Va. Code § 11-4.1"},
    "AZ": {"rule": "own_negligence_void", "statute": "Ariz. Rev. Stat. § 32-1159"},
    "MI": {"rule": "sole_negligence_void", "statute": "Mich. Comp. Laws § 691.991"},
    "IN": {"rule": "sole_negligence_void", "statute": "Ind. Code § 26-2-5-1"},
}

# Verdicts. Wording is deliberately hedged — these render as "likely …", never
# as a bare legal conclusion, because we are not counsel.
VERDICT_VOID = "likely_void_by_statute"
VERDICT_UNINSURABLE = "uninsurable_exposure"
VERDICT_INSURABLE = "insurable"
VERDICT_REVIEW = "review"

VERDICT_LABEL = {
    VERDICT_VOID: "Likely void by statute",
    VERDICT_UNINSURABLE: "Uninsurable exposure",
    VERDICT_INSURABLE: "Insurable",
    VERDICT_REVIEW: "Needs review",
}
VERDICT_TONE = {
    VERDICT_VOID: "bad",
    VERDICT_UNINSURABLE: "bad",
    VERDICT_INSURABLE: "good",
    VERDICT_REVIEW: "muted",
}


def _norm_state(v) -> Optional[str]:
    s = str(v or "").strip().upper()
    return s if len(s) == 2 and s.isalpha() else None


# The CGL insured-contract analysis is state-independent: a broad-form clause
# reaching the counterparty's SOLE negligence is uninsurable no matter which
# statute governs enforceability. One text, three verdict paths.
_BROAD_CGL_BASIS = (
    "Broad-form indemnity: the client would owe the counterparty even for the "
    "counterparty's SOLE negligence. That promise falls outside the CGL "
    "\"insured contract\" definition — the client funds it personally. Negotiate to "
    "intermediate or limited form."
)


def is_provisional(contract: dict) -> bool:
    """Provisional = AI-extracted terms a human hasn't vouched for yet.

    Manually-keyed contracts (``ai_available`` false) are human-authored — there
    are no "extracted terms" to confirm, so they are never provisional."""
    return bool(contract.get("ai_available")) and not contract.get("confirmed_at")


def _controlling_state(contract_type: Optional[str], governing_state: Optional[str],
                       project_state: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Which state's anti-indemnity statute governs → ``(state, blocker_note)``.

    Construction: the project state controls, full stop — anti-indemnity
    statutes are anti-waiver, so a choice-of-law clause does not escape the
    statute where the work is performed. A missing project state therefore
    BLOCKS the verdict (note returned) rather than falling back to the
    governing-law state: the governing state is exactly the input those
    statutes are designed to ignore, so a confident verdict built on it would
    be wrong in the worst way. When both states are known, mapped, and disagree
    on the rule, we also block with a note — the honest answer is "a lawyer
    must resolve this", not a coin flip.
    """
    gov, proj = _norm_state(governing_state), _norm_state(project_state)
    if contract_type == "construction":
        if not proj:
            return None, (
                "No project/premises state is recorded. Construction anti-indemnity statutes "
                "attach to where the work is performed"
                + (f" — the governing-law state ({gov}) cannot substitute for it" if gov else "")
                + ". Record the project state on this contract to get a verdict."
            )
        if gov and proj != gov:
            r_proj = (_STATE_ANTI_INDEMNITY.get(proj) or {}).get("rule")
            r_gov = (_STATE_ANTI_INDEMNITY.get(gov) or {}).get("rule")
            if r_proj and r_gov and r_proj != r_gov:
                return None, (
                    f"Work is performed in {proj} but the contract selects {gov} law, and the two "
                    f"states' anti-indemnity statutes differ. Most construction anti-indemnity "
                    f"statutes are anti-waiver, so {proj} likely controls — confirm with counsel."
                )
        return proj, None
    return gov or proj, None


def assess_indemnity(risk_transfer: Optional[dict], *, governing_state: Optional[str] = None,
                     project_state: Optional[str] = None,
                     contract_type: Optional[str] = None) -> dict:
    """Pure verdict on one contract's indemnity clause.

    Returns ``{verdict, basis, statute, controlling_state}``. Never raises.
    """
    rt = risk_transfer if isinstance(risk_transfer, dict) else {}
    ind = rt.get("indemnity") if isinstance(rt.get("indemnity"), dict) else rt

    def out(verdict, basis, statute=None, state=None):
        return {"verdict": verdict, "basis": basis, "statute": statute, "controlling_state": state}

    if not ind or not ind.get("present"):
        return out(VERDICT_REVIEW, "No indemnification clause was extracted from this contract.")

    form = str(ind.get("form") or "unclear").lower()
    if form not in INDEMNITY_FORMS or form == "unclear":
        return out(VERDICT_REVIEW, "The indemnity clause's scope could not be classified. Read the clause directly.")

    direction = str(ind.get("direction") or "unclear").lower()
    if direction == "they_indemnify_us":
        return out(VERDICT_INSURABLE,
                   "The counterparty indemnifies the client, not the reverse — this transfers risk "
                   "toward the client, not away from it. No insurability exposure.")
    if direction not in ("we_indemnify_them", "mutual"):
        # Unknown direction means we don't know whose exposure this is — a
        # confident void/uninsurable verdict here would be built on a guess.
        return out(VERDICT_REVIEW,
                   "The clause's direction — who indemnifies whom — could not be determined. "
                   "Confirm the direction to get a verdict.")

    # A non-broad form that "covers sole negligence" is a contradiction — by
    # definition only broad form reaches the indemnitee's sole negligence. A
    # contradictory extraction gets no confident verdict in either direction.
    if form != "broad" and ind.get("covers_sole_negligence"):
        return out(VERDICT_REVIEW,
                   f"The extraction is contradictory: the clause was classified {form}-form, which by "
                   f"definition does not reach the counterparty's sole negligence, yet the "
                   f"sole-negligence flag is set. Read the clause directly and correct one of the two.")
    covers_sole = form == "broad"

    state, blocker = _controlling_state(contract_type, governing_state, project_state)

    if contract_type == "construction":
        # Enforceability turns on the project state's anti-indemnity statute.
        # Insurability does NOT — so a missing/unmapped state blocks only the
        # *void* half of the analysis, never the state-independent CGL half.
        row = _STATE_ANTI_INDEMNITY.get(state) if state else None
        if blocker or not row:
            unresolved = blocker or (
                f"{state}'s anti-indemnity statute is not in our reference table, so its "
                f"enforceability is unresolved here."
            )
            if covers_sole:
                return out(VERDICT_UNINSURABLE, f"{_BROAD_CGL_BASIS} Separately: {unresolved}", state=state)
            return out(VERDICT_REVIEW, unresolved, state=state)
        rule, statute = row["rule"], row["statute"]
        if covers_sole and rule in ("own_negligence_void", "sole_negligence_void"):
            return out(VERDICT_VOID,
                       f"The clause indemnifies the counterparty for its own sole negligence. Under "
                       f"{statute}, {state} voids that in construction contracts — the client may be "
                       f"promising something unenforceable, and no insurer will fund it.",
                       statute, state)
        if form == "intermediate" and rule == "own_negligence_void":
            return out(VERDICT_VOID,
                       f"The clause reaches the counterparty's partial (concurrent) negligence. Under "
                       f"{statute}, {state} voids indemnity for any of the indemnitee's own negligence "
                       f"in construction contracts.",
                       statute, state)
        if form == "intermediate":
            return out(VERDICT_INSURABLE,
                       f"Intermediate-form indemnity. {statute} voids only sole-negligence indemnity in "
                       f"{state}, so this clause survives and sits inside the CGL insured-contract scope.",
                       statute, state)
        if covers_sole:
            # A `rule: "none"` state — the statute doesn't void the clause, but the
            # CGL insured-contract grant still won't fund sole-negligence indemnity.
            # Without this, broad form falls through to the limited-form return below.
            return out(VERDICT_UNINSURABLE,
                       f"{_BROAD_CGL_BASIS} {statute} does not void it in {state}, so the client would "
                       f"be bound to a promise no policy responds to.",
                       statute, state)
        return out(VERDICT_INSURABLE,
                   f"Limited-form indemnity — the client answers only for its own negligence. "
                   f"Enforceable in {state} and covered as an insured contract.",
                   statute, state)

    # Non-construction: the anti-indemnity statutes above don't reach these, so
    # the question is purely insurability under the CGL insured-contract grant —
    # which is state-independent. An unmapped (or even absent) state must not
    # suppress this analysis.
    if covers_sole:
        return out(VERDICT_UNINSURABLE, _BROAD_CGL_BASIS, state=state)
    if form == "intermediate":
        return out(VERDICT_INSURABLE,
                   "Intermediate-form indemnity — within the CGL insured-contract grant, so the "
                   "policy responds to the assumed liability.",
                   state=state)
    return out(VERDICT_INSURABLE,
               "Limited-form indemnity — the client answers only for its own negligence.",
               state=state)


def _actions(review: dict, indemnity: dict, contract: dict) -> list[str]:
    """Concrete, insurance-lane next steps. Ordered hardest-first."""
    acts: list[str] = []
    v = indemnity.get("verdict")
    if v == VERDICT_VOID:
        acts.append("Strike or narrow the indemnity clause — as written it is likely unenforceable "
                    "in the controlling state, and no policy will fund it.")
    elif v == VERDICT_UNINSURABLE:
        acts.append("Negotiate the indemnity down to intermediate or limited form so the CGL "
                    "insured-contract grant responds.")
    elif v == VERDICT_REVIEW:
        acts.append("Resolve the indemnity clause — record the governing/project state and confirm "
                    "the extracted clause, or read it directly.")

    for line in review.get("lines") or []:
        if line.get("status") in ("no_coverage", "shortfall") and line.get("gap"):
            acts.append(f"{line['label']}: {line['gap']}.")
        for eg in line.get("endorsement_gaps") or []:
            acts.append(f"{line['label']}: obtain {eg['label'].lower()} endorsement — required by this contract.")

    if is_provisional(contract):
        acts.append("Confirm the extracted terms to lift the provisional label from this review.")
    return acts


def review_contract(contract: dict, carried: list[dict], *, headcount: Optional[int] = None,
                    venue_tier: Optional[str] = None, industry: Optional[str] = None) -> dict:
    """The per-contract, pre-signature deliverable: compliant / exposed / actions.

    Distinct from ``limit_adequacy.build_review``, which rolls EVERY contract into
    a portfolio worst-case. Here we diff carried limits against **this contract
    alone** — reusing ``limit_adequacy.analyze`` with a one-element contract list,
    which is exactly what ``_max_required`` computes over a single contract.
    """
    review = la.analyze(carried, [contract], headcount=headcount,
                        venue_tier=venue_tier, industry=industry)

    indemnity = assess_indemnity(
        contract.get("risk_transfer"),
        governing_state=contract.get("governing_state"),
        project_state=contract.get("project_state"),
        contract_type=contract.get("contract_type"),
    )

    exposed = [l for l in review["lines"] if l.get("status") in ("no_coverage", "shortfall")]
    endorse = sum(len(l.get("endorsement_gaps") or []) for l in review["lines"])
    compliant = [l for l in review["lines"]
                 if l.get("status") == "ok" and (l.get("carried") or l.get("contract_required"))]

    return {
        "contract": {
            "id": contract.get("id"),
            "name": contract.get("name"),
            "counterparty": contract.get("counterparty"),
            "contract_type": contract.get("contract_type"),
            "governing_state": contract.get("governing_state"),
            "project_state": contract.get("project_state"),
            "status": contract.get("status"),
            "confirmed_at": contract.get("confirmed_at"),
            "has_source": bool(contract.get("has_source")),
        },
        "lines": review["lines"],
        "indemnity": indemnity,
        "risk_transfer": contract.get("risk_transfer") or {},
        "summary": {
            "exposed": len(exposed),
            "compliant": len(compliant),
            "endorsement_gaps": endorse,
            "indemnity_verdict": indemnity["verdict"],
        },
        "actions": _actions(review, indemnity, contract),
        # Verdicts computed from an unconfirmed AI extraction are provisional —
        # the human hasn't yet vouched for the clause we read.
        "provisional": is_provisional(contract),
        "disclaimer": DISCLAIMER,
    }


async def build_contract_review(conn, company_id, contract_id) -> Optional[dict]:
    """DB wrapper: one contract + the company's carried lines → ``review_contract``.

    Returns None when the contract doesn't belong to the company (404 upstream).
    """
    row = await conn.fetchrow(
        f"SELECT {_CONTRACT_COLS} FROM company_contracts WHERE id = $1 AND company_id = $2",
        contract_id, company_id,
    )
    if not row:
        return None
    contract = la._contract_row(row)

    carried = [dict(r) for r in await conn.fetch(
        """SELECT line, carrier, per_occurrence, aggregate, retention,
                  additional_insured, waiver_of_subrogation, primary_noncontributory,
                  effective_date, expiry_date, note
           FROM company_coverage_lines WHERE company_id = $1 ORDER BY line""",
        company_id,
    )]

    headcount = industry = None
    company = None
    try:
        company = await conn.fetchrow("SELECT name, industry FROM companies WHERE id = $1", company_id)
        industry = company["industry"] if company else None
        prof = await conn.fetchrow(
            "SELECT headcount FROM company_handbook_profiles WHERE company_id = $1", company_id
        )
        headcount = prof["headcount"] if prof else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("risk_transfer: profile lookup failed: %s", exc)

    venue_tier = None
    try:
        from . import venue_severity
        venue = await venue_severity.company_venue_exposure(conn, company_id)
        venue_tier = (venue.get("summary") or {}).get("worst_tier") if venue else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("risk_transfer: venue lookup failed: %s", exc)

    out = review_contract(contract, carried, headcount=headcount,
                          venue_tier=venue_tier, industry=industry)
    out["company_name"] = (company["name"] if company else "Client")
    return out


# --- shared contract store (tenant + broker routes call these) --------------

def validate_pdf_upload(file: UploadFile) -> None:
    """Reject anything that isn't a PDF, before we read it. Shared by the tenant
    and broker upload endpoints so the two can't drift."""
    is_pdf = (file.content_type == "application/pdf") or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Upload a PDF contract")


def validate_pdf_bytes(data: bytes) -> None:
    """Size/emptiness guard applied after the body is read."""
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_CONTRACT_BYTES:
        raise HTTPException(status_code=413, detail="PDF too large (max 15 MB)")


async def store_uploaded_contract(conn, company_id, user_id, data: bytes, filename: str) -> dict:
    """Parse an uploaded contract PDF, retain the source, insert the draft row.

    The source PDF is kept (private bucket) so a clause finding stays verifiable.
    S3 being unconfigured is not an error — ``upload_private_file`` raises
    ``RuntimeError`` on a bare local dev box, and losing the blob is strictly
    better than losing the review, so we degrade to limadq01's parse-and-discard.
    """
    parsed = await contract_parser.parse_contract(data)
    fname = (filename or "contract.pdf")[:255]
    name = (parsed.get("counterparty") or fname.rsplit(".", 1)[0])[:255]
    status = "parsed" if parsed["available"] else "error"

    storage_path = None
    try:
        storage_path = await get_storage().upload_private_file(
            data, fname, prefix="contracts", content_type="application/pdf",
            # Counterparty contracts get their own bucket — they are third-party
            # legal documents, not our employees' records. Unset → shared bucket.
            bucket=get_settings().s3_contracts_bucket,
        )
    except Exception as exc:  # noqa: BLE001 - retention is best-effort
        logger.warning("risk_transfer: contract source not retained (%s)", exc)

    try:
        row = await conn.fetchrow(
            f"""INSERT INTO company_contracts
                 (company_id, name, counterparty, status, requirements, ai_available,
                  source_filename, uploaded_by, contract_type, governing_state,
                  project_state, storage_path, risk_transfer)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
               RETURNING {_CONTRACT_COLS}""",
            company_id, name, parsed.get("counterparty"), status,
            json.dumps(parsed["requirements"]), parsed["available"], fname, user_id,
            parsed.get("contract_type"), parsed.get("governing_state"), parsed.get("project_state"),
            storage_path,
            json.dumps(parsed["risk_transfer"]) if parsed.get("risk_transfer") else None,
        )
    except Exception:
        # No row will ever reference the blob we just wrote — don't leave it behind.
        if storage_path:
            await discard_source(storage_path)
        raise
    return la._contract_row(row)


async def discard_source(storage_path: Optional[str]) -> None:
    """Best-effort delete of a retained source PDF. ``delete_file`` parses the
    bucket back out of the ``s3://`` URI, so a contract written before the
    contracts bucket existed still deletes from wherever it actually lives."""
    if not storage_path:
        return
    try:
        await get_storage().delete_file(storage_path)
    except Exception as exc:  # noqa: BLE001 - cleanup must never fail the caller
        logger.warning("risk_transfer: contract source not deleted (%s)", exc)


def normalize_requirements(requirements) -> list[dict]:
    """Pydantic requirement models → stored shape, with line keys normalized."""
    out: list[dict] = []
    for r in requirements or []:
        line = la.normalize_line(r.line)
        if not line:
            continue
        out.append({
            "line": line, "per_occurrence": r.per_occurrence, "aggregate": r.aggregate,
            "additional_insured": r.additional_insured,
            "waiver_of_subrogation": r.waiver_of_subrogation,
            "primary_noncontributory": r.primary_noncontributory,
            "note": r.note, "quote": r.quote, "page": r.page,
        })
    return out


# Columns whose value the confirmation vouches for. The verdict is a function of
# the clause AND the controlling state AND the contract type, so confirming it
# vouches for all three: editing the project state of a confirmed contract can
# flip `insurable` → `likely_void_by_statute`, and presenting that as
# reviewer-vouched would be a lie. Cosmetic edits (name, counterparty,
# requirements) leave the confirmation intact.
_VERDICT_INPUTS = ("contract_type", "governing_state", "project_state", "risk_transfer")


async def update_contract(conn, company_id, contract_id, body) -> Optional[dict]:
    """Patch a contract. Changing any **verdict input** resets ``confirmed_at``.

    PATCH semantics are driven by Pydantic's ``model_fields_set``, not by
    null-checks: a field the caller didn't send is left alone, and a field sent
    explicitly as null is CLEARED. (A mis-extracted ``project_state`` has to be
    removable — it is the single load-bearing input for every construction
    verdict.) The confirmation resets only when a verdict input's value actually
    CHANGES, so re-sending the same ``contract_type`` while renaming a contract
    no longer silently un-confirms it.
    """
    existing = await conn.fetchrow(
        f"SELECT {_CONTRACT_COLS} FROM company_contracts WHERE id = $1 AND company_id = $2",
        contract_id, company_id,
    )
    if not existing:
        return None
    current = la._contract_row(existing)

    sent = body.model_fields_set
    incoming: dict = {}
    if "name" in sent:
        incoming["name"] = body.name
    if "counterparty" in sent:
        incoming["counterparty"] = body.counterparty
    if "requirements" in sent:
        incoming["requirements"] = normalize_requirements(body.requirements)
    if "contract_type" in sent:
        incoming["contract_type"] = body.contract_type
    # States are normalized on write — a value `_norm_state` would reject must not
    # persist only to read back as "unmapped" at verdict time.
    if "governing_state" in sent:
        incoming["governing_state"] = _norm_state(body.governing_state)
    if "project_state" in sent:
        incoming["project_state"] = _norm_state(body.project_state)
    if "risk_transfer" in sent:
        incoming["risk_transfer"] = None if body.risk_transfer is None else body.risk_transfer.model_dump()

    if not incoming:
        return current

    reset = any(k in incoming and incoming[k] != current.get(k) for k in _VERDICT_INPUTS)

    # jsonb columns need an explicit cast and a serialized value; everything else
    # binds straight through.
    _JSONB = {"requirements", "risk_transfer"}
    sets, args = [], [contract_id, company_id]
    for col, val in incoming.items():
        args.append(json.dumps(val) if col in _JSONB and val is not None else val)
        sets.append(f"{col} = ${len(args)}" + ("::jsonb" if col in _JSONB else ""))
    if "requirements" in incoming:
        sets.append("status = CASE WHEN status = 'error' THEN 'manual' ELSE status END")
    if reset:
        sets.append("confirmed_at = NULL")
        sets.append("confirmed_by = NULL")
    sets.append("updated_at = NOW()")

    row = await conn.fetchrow(
        f"""UPDATE company_contracts SET {', '.join(sets)}
            WHERE id = $1 AND company_id = $2
            RETURNING {_CONTRACT_COLS}""",
        *args,
    )
    return la._contract_row(row) if row else None


async def confirm_contract(conn, company_id, contract_id, user_id) -> Optional[dict]:
    """Human vouches for the extraction → verdict stops being provisional."""
    row = await conn.fetchrow(
        f"""UPDATE company_contracts
              SET confirmed_at = NOW(), confirmed_by = $3, updated_at = NOW()
            WHERE id = $1 AND company_id = $2
            RETURNING {_CONTRACT_COLS}""",
        contract_id, company_id, user_id,
    )
    return la._contract_row(row) if row else None


async def contract_source_url(conn, company_id, contract_id) -> Optional[str]:
    """Presigned URL for the retained source PDF, or None. ``get_presigned_download_url``
    is synchronous — don't await it."""
    path = await conn.fetchval(
        "SELECT storage_path FROM company_contracts WHERE id = $1 AND company_id = $2",
        contract_id, company_id,
    )
    if not path:
        return None
    return get_storage().get_presigned_download_url(path)


# --- deterministic per-contract review PDF ----------------------------------

_esc = la._esc  # one escaper across both contract-review surfaces

_FORM_LABEL = {"broad": "Broad form", "intermediate": "Intermediate form",
               "limited": "Limited form", "unclear": "Unclassified"}
_DIR_LABEL = {"we_indemnify_them": "Client indemnifies counterparty",
              "they_indemnify_us": "Counterparty indemnifies client",
              "mutual": "Mutual", "unclear": "Unclear"}


def _indemnity_html(review: dict) -> str:
    ind = review.get("indemnity") or {}
    rt = (review.get("risk_transfer") or {}).get("indemnity") or {}
    if not rt.get("present"):
        return "<p class='muted'>No indemnification clause was extracted from this contract.</p>"
    quote = rt.get("quote")
    page = rt.get("page")
    rows = [
        ("Form", _FORM_LABEL.get(rt.get("form"), "Unclassified")),
        ("Direction", _DIR_LABEL.get(rt.get("direction"), "Unclear")),
        ("Covers counterparty's sole negligence", "Yes" if rt.get("covers_sole_negligence") else "No"),
        ("Duty to defend", "Yes" if rt.get("defense_obligation") else "No"),
        ("Controlling state", ind.get("controlling_state") or "—"),
        ("Statute", ind.get("statute") or "—"),
    ]
    body = "".join(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in rows)
    tone = VERDICT_TONE.get(ind.get("verdict"), "muted")
    out = (
        f"<p class='verdict {tone}'>{_esc(VERDICT_LABEL.get(ind.get('verdict'), 'Needs review'))}</p>"
        f"<p class='basis'>{_esc(ind.get('basis'))}</p>"
        f"<table><tbody>{body}</tbody></table>"
    )
    if quote:
        anchor = f" (p. {page})" if page else ""
        out += f"<div class='quote'>&ldquo;{_esc(quote)}&rdquo;<span class='pg'>{_esc(anchor)}</span></div>"
    return out


def _contract_review_html(review: dict) -> str:
    c = review.get("contract") or {}
    s = review.get("summary") or {}
    lines = [l for l in (review.get("lines") or []) if l.get("carried") or l.get("contract_required")]
    rows = "".join(
        f"<tr><td>{_esc(l['label'])}</td>"
        f"<td class='r'>{la._money((l.get('carried') or {}).get('per_occurrence')) if l.get('carried') else '—'}</td>"
        f"<td class='r'>{la._money((l.get('contract_required') or {}).get('per_occurrence')) if l.get('contract_required') else '—'}</td>"
        f"<td class='st {la._STATUS_CLASS.get(l['status'], 'muted')}'>{la._STATUS_LABEL.get(l['status'], '')}</td>"
        f"<td>{_esc(l.get('gap'))}</td></tr>"
        for l in lines
    ) or "<tr><td colspan='5'>No coverage lines on file</td></tr>"
    actions = "".join(f"<li>{_esc(a)}</li>" for a in review.get("actions") or []) or "<li>No action required.</li>"
    provisional = (
        "<div class='prov'>PROVISIONAL — the extracted terms have not been confirmed by a reviewer.</div>"
        if review.get("provisional") else ""
    )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }}
      h1 {{ color:#1f8a5b; margin:0 0 2px; font-size:22px; }}
      .sub {{ color:#666; margin:0 0 12px; }}
      h2 {{ font-size:13px; border-bottom:2px solid #1f8a5b; padding-bottom:4px; margin:18px 0 8px; }}
      .prov {{ background:#fff8e1; border:1px solid #e6c65c; color:#7a5c00; padding:6px 10px;
               border-radius:6px; font-size:9px; font-weight:700; letter-spacing:.4px; margin-bottom:10px; }}
      .grid {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
      .cell {{ border:1px solid #e5e7eb; border-radius:8px; padding:8px 12px; min-width:100px; }}
      .cell .l {{ font-size:8px; text-transform:uppercase; letter-spacing:.6px; color:#888; }}
      .cell .v {{ font-size:18px; font-weight:300; font-family:monospace; margin-top:3px; }}
      table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
      th {{ text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:4px 6px; }}
      td {{ padding:4px 6px; border-bottom:1px solid #f0f0f0; }}
      td.r {{ text-align:right; font-family:monospace; }}
      .st {{ font-size:8px; font-weight:700; }}
      .st.good{{color:#1f8a5b}} .st.warn{{color:#b8902f}} .st.bad{{color:#b23b3b}} .st.muted{{color:#999}}
      .verdict {{ font-size:14px; font-weight:700; margin:2px 0 4px; }}
      .verdict.good{{color:#1f8a5b}} .verdict.bad{{color:#b23b3b}} .verdict.muted{{color:#777}}
      .basis {{ color:#444; margin:0 0 8px; }}
      .muted {{ color:#888; }}
      .quote {{ border-left:3px solid #ddd; padding:6px 10px; margin-top:8px; color:#333;
                background:#fafafa; font-style:italic; }}
      .quote .pg {{ font-style:normal; color:#999; font-size:9px; }}
      ol {{ margin:4px 0 0 16px; padding:0; }} li {{ margin-bottom:3px; }}
      .foot {{ margin-top:24px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }}
    </style></head><body>
      <h1>Contract Review</h1>
      <p class="sub">{_esc(review.get('company_name'))} — {_esc(c.get('name'))}
        {(' · ' + _esc(c.get('counterparty'))) if c.get('counterparty') else ''}</p>
      {provisional}

      <h2>Summary</h2>
      <div class="grid">
        <div class="cell"><div class="l">Exposed lines</div><div class="v">{_esc(s.get('exposed'))}</div></div>
        <div class="cell"><div class="l">Compliant lines</div><div class="v">{_esc(s.get('compliant'))}</div></div>
        <div class="cell"><div class="l">Endorsement gaps</div><div class="v">{_esc(s.get('endorsement_gaps'))}</div></div>
      </div>

      <h2>Indemnification &amp; risk transfer</h2>
      {_indemnity_html(review)}

      <h2>Insurance requirements vs. carried limits</h2>
      <table><thead><tr><th>Line</th><th class="r">Carried</th><th class="r">This contract requires</th>
        <th>Status</th><th>Gap</th></tr></thead><tbody>{rows}</tbody></table>

      <h2>Actions</h2>
      <ol>{actions}</ol>

      <div class="foot">{_esc(DISCLAIMER)} Prepared by Matcha. Requirements and clause text were extracted
      from the uploaded contract{' and confirmed by a reviewer' if not review.get('provisional') else ''};
      confirm limits and endorsements against the policy declarations.</div>
    </body></html>"""


async def render_contract_review_pdf(review: dict) -> bytes:
    def _render() -> bytes:
        from weasyprint import HTML

        return HTML(string=_contract_review_html(review), url_fetcher=safe_url_fetcher).write_pdf()

    return await asyncio.to_thread(_render)
