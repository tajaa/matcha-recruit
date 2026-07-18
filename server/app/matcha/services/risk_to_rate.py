"""Risk-to-Rate — turn a client's verified risk record into carrier credit levers.

The premium-credit half of the broker carrier hub: a business's operational
controls (training, discipline, safety programs, wage/hour, incident response,
credentialing, anti-harassment policy + signatures) are exactly what a carrier
rewards. This reads the *already-computed*, verified signals the platform holds —
via ``epl_readiness`` + ``controls_evidence`` — and maps them to ranked credit
levers: what's already earning a credit (realized) and what would earn one if
closed (available).

Two layers, mirroring ``coterie_service``:
- ``score_levers`` — PURE (no DB): status maps -> ranked levers + credit rollup.
  Unit-tested without a database.
- ``build`` — gathers the signals for a company and calls ``score_levers``.

The credit magnitudes are **directional** (a deterministic in-house estimate),
NOT carrier-quoted, until the ``credits`` capability is live — at which point the
same levers carry carrier-returned numbers. Never an LLM; fully deterministic.
"""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

# A lever is realized when its underlying control/factor is satisfied. Each names
# the candidate signal keys it may appear under across epl_readiness / controls.
_LEVER_CATALOG = [
    {"key": "safety_programs", "label": "Documented safety programs", "bps": 200,
     "signals": ["safety_programs", "safety_program"]},
    {"key": "anti_harassment", "label": "Anti-harassment policy + signed acknowledgements", "bps": 150,
     "signals": ["anti_harassment_policy", "anti_harassment", "harassment_policy", "handbook"]},
    {"key": "training", "label": "Harassment-prevention training current", "bps": 150,
     "signals": ["training", "harassment_training"]},
    {"key": "incident_response", "label": "IR / OSHA incident-response program", "bps": 125,
     "signals": ["incident_response", "ir_osha", "osha", "incidents"]},
    {"key": "wage_hour", "label": "Multi-state wage & hour controls", "bps": 100,
     "signals": ["wage_hour", "multistate_wage_hour", "wage_and_hour"]},
    {"key": "progressive_discipline", "label": "Progressive discipline documented", "bps": 100,
     "signals": ["discipline", "progressive_discipline"]},
    {"key": "credentialing", "label": "Credentialing currency", "bps": 75,
     "signals": ["credentialing", "credential_currency", "credentials"]},
]

# Statuses that count as "this control is in place / earning a credit".
_SATISFIED = {"in_place", "verified", "complete", "completed", "current", "yes",
              "true", "pass", "derived", "met", "ok"}


def _norm(v) -> str:
    return str(v or "").strip().lower()


def score_levers(status_by_key: dict, readiness_score=None) -> dict:
    """Rank the credit levers from a flat ``{signal_key: status}`` map.

    ``status_by_key`` merges the epl-factor and controls-register statuses. A lever
    is *realized* if any of its candidate signals is satisfied, *available* if a
    signal is present but not satisfied, and available/`not_tracked` if the client
    tracks nothing for it yet.
    """
    norm = {_norm(k): _norm(v) for k, v in (status_by_key or {}).items()}
    levers, realized_bps, available_bps = [], 0, 0
    for spec in _LEVER_CATALOG:
        present = [norm[s] for s in spec["signals"] if s in norm]
        realized = any(st in _SATISFIED for st in present)
        if realized:
            realized_bps += spec["bps"]
            basis = "in_place"
        else:
            available_bps += spec["bps"]
            basis = "gap" if present else "not_tracked"
        levers.append({
            "key": spec["key"], "label": spec["label"],
            "status": "realized" if realized else "available",
            "est_credit_bps": spec["bps"], "basis": basis,
        })
    # available first (the action list), then realized; each block by credit size.
    levers.sort(key=lambda l: (l["status"] != "available", -l["est_credit_bps"]))
    return {
        "levers": levers,
        "realized_credit_bps": realized_bps,
        "available_credit_bps": available_bps,
        "total_credit_bps": realized_bps + available_bps,
        "readiness_score": readiness_score,
    }


async def build(conn, company_id: UUID) -> dict:
    """Gather a company's verified signals and score the credit levers. Best-effort
    per source — a missing subsystem degrades that lever to available, never 500s."""
    from . import epl_readiness, controls_evidence as ce, submission_readiness as sr

    status_by_key: dict = {}
    epl = None
    try:
        epl = await epl_readiness.compute_epl_readiness(conn, company_id)
        for f in (epl.get("factors") or []):
            key = f.get("key") or f.get("id")
            if key:
                status_by_key[key] = f.get("status")
    except Exception as exc:  # noqa: BLE001 - one source failing must not sink the read
        logger.warning("risk_to_rate: epl signals failed for %s: %s", company_id, exc)

    try:
        register = await ce.build_register(conn, company_id, epl=epl) if epl else await ce.build_register(conn, company_id)
        for c in (register.get("controls") or []):
            key = c.get("key") or c.get("id")
            if key:
                # controls carry a verified flag and/or a status string
                status_by_key[key] = c.get("status") or ("verified" if c.get("verified") else c.get("state"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("risk_to_rate: controls signals failed for %s: %s", company_id, exc)

    readiness_score = None
    try:
        readiness = await sr.compute_readiness(conn, company_id)
        readiness_score = (readiness or {}).get("score")
    except Exception as exc:  # noqa: BLE001
        logger.warning("risk_to_rate: readiness failed for %s: %s", company_id, exc)

    return score_levers(status_by_key, readiness_score=readiness_score)
