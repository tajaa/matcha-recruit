"""D&O / Management-liability readiness scoring.

Directors & Officers liability is underwritten on governance + financial health,
not the HR-hygiene data EPL uses — so, unlike ``epl_readiness``, there is no
operational Matcha source to derive these factors from. Every factor is
attested (business records it during a review; broker records it off-platform),
stored in ``company_do_attestations``. Same weighted-composite / band / top-gap
machinery as EPL so the score reads the same way on the submission.

Composite = weighted sum of attested sub-scores (0-100). Caller owns the conn.
"""

from typing import Any, Optional
from uuid import UUID

from .epl_readiness import (
    readiness_band, _factor_band, top_gap, _serialize_attestation,
    _ATTEST_SCORE, ATTESTATION_STATUSES,
)

# Factor catalog — weights sum to 100. All attested (no derived source for D&O).
FACTORS: list[dict[str, Any]] = [
    {"key": "board_governance",  "label": "Board governance & independence",  "weight": 25, "kind": "attested"},
    {"key": "financial_health",  "label": "Financial health / audited financials", "weight": 25, "kind": "attested"},
    {"key": "erisa_fiduciary",   "label": "ERISA / fiduciary controls",       "weight": 20, "kind": "attested"},
    {"key": "bankruptcy_ma",     "label": "Bankruptcy / M&A exposure",        "weight": 15, "kind": "attested"},
    {"key": "claims_history",    "label": "Prior D&O claims history",         "weight": 15, "kind": "attested"},
]

_STATUS_DETAIL = {
    "in_place": "Attested: in place", "partial": "Attested: partial",
    "gap": "Attested: gap", "unknown": "Not yet reviewed",
}


async def get_attestations(conn, company_id: UUID) -> dict[str, dict]:
    """item_key → attestation row for a company."""
    rows = await conn.fetch(
        "SELECT item_key, status, note, updated_at FROM company_do_attestations WHERE company_id = $1",
        company_id,
    )
    return {r["item_key"]: _serialize_attestation(r) for r in rows}


def _assemble_do(factor_inputs: dict[str, dict]) -> dict:
    """Composite + per-factor breakdown from attested factor inputs. Pure.

    Only ``assessed`` factors (status reviewed, not 'unknown') contribute; the
    rest renormalize instead of being scored as a confirmed 0.
    """
    factors: list[dict] = []
    composite = 0.0
    assessed_weight = 0.0
    for f in FACTORS:
        inp = factor_inputs[f["key"]]
        sub, detail, att, assessed = inp["score"], inp["detail"], inp["attestation"], inp["assessed"]
        contribution = f["weight"] * sub / 100.0
        if assessed:
            composite += contribution
            assessed_weight += f["weight"]
        factors.append({
            "key": f["key"], "label": f["label"], "kind": "attested", "weight": f["weight"],
            "score": sub, "status": _factor_band(sub), "contribution": round(contribution, 1),
            "detail": detail, "attestation": att, "assessed": assessed,
        })
    score = round(100 * composite / assessed_weight) if assessed_weight else 0
    return {
        "score": score,
        "band": readiness_band(score),
        "attested_max": round(assessed_weight),
        "assessed_weight": round(assessed_weight),
        "coverage": round(assessed_weight / 100, 2),
        "factors": factors,
    }


async def compute_do_readiness(conn, company_id: UUID) -> dict:
    """Full D&O readiness for one company: composite + per-factor breakdown."""
    attestations = await get_attestations(conn, company_id)
    factor_inputs: dict[str, dict] = {}
    for f in FACTORS:
        a = attestations.get(f["key"])
        status = a["status"] if a else "unknown"
        factor_inputs[f["key"]] = {
            "score": _ATTEST_SCORE.get(status, 0),
            "detail": _STATUS_DETAIL.get(status, _STATUS_DETAIL["unknown"]),
            "attestation": a or {"item_key": f["key"], "status": "unknown", "note": None, "updated_at": None},
            "assessed": status != "unknown",
        }
    return {"company_id": str(company_id), **_assemble_do(factor_inputs)}


def assess_from_statuses(statuses: dict) -> dict:
    """D&O assessment from broker-attested statuses only (off-platform clients).

    ``statuses`` maps item_key -> status; missing factors default to 'unknown'
    and are excluded from the composite (renormalized), matching the tenant path.
    """
    factor_inputs: dict[str, dict] = {}
    for f in FACTORS:
        status = statuses.get(f["key"]) or "unknown"
        if status not in ATTESTATION_STATUSES:
            status = "unknown"
        factor_inputs[f["key"]] = {
            "score": _ATTEST_SCORE.get(status, 0),
            "detail": _STATUS_DETAIL.get(status, _STATUS_DETAIL["unknown"]),
            "attestation": {"item_key": f["key"], "status": status, "note": None, "updated_at": None},
            "assessed": status != "unknown",
        }
    return _assemble_do(factor_inputs)


def do_top_gap(assessment: dict) -> Optional[dict]:
    """Headline D&O gap — reuses the EPL top_gap logic (weight × shortfall)."""
    return top_gap(assessment)
