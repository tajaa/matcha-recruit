"""Submission-readiness score — the data→price proof loop.

Distinct from ``risk_index`` (which scores how *good* the risk is): this scores
how *complete and underwriter-ready* the company's WC + EPL data is. The report's
core causal claim — a low-risk company with thin, poorly-articulated data still
gets worse terms ("buyers unable to articulate their exposure get worse
pricing", WTW p.4/p.11). The output is a 0-100 completeness score + a checklist
of concrete "finish these N items → tighter terms" actions, each tied to an
existing Matcha surface (record your mod, map class codes, answer the EPL
questionnaire, verify your controls, …).

Reuses the same inputs the submission packet is built from. Pure ``evaluate`` is
unit-testable; ``compute_readiness`` gathers the signals (and accepts precomputed
``wc``/``epl``/``controls`` so the broker submission path doesn't recompute them).
"""

from uuid import UUID

from . import epl_readiness, wc_depth, controls_evidence


def readiness_band(score: int) -> str:
    if score >= 80:
        return "ready"
    if score >= 50:
        return "developing"
    return "thin"


def evaluate(
    *,
    states_count: int,
    headcount,
    industry,
    experience_mod_present: bool,
    recordable_cases: int,
    untyped_recordables: int,
    lost_time_cases: int,
    rtw_resolved: int,
    rtw_avg_days,
    class_count: int,
    epl_unknown_count: int,
    ah_policy_score: int,
    controls_verified_count: int,
    controls_unverified_count: int,
) -> dict:
    """Pure scoring over gathered signals. Weights sum to 100 (score == weighted %)."""
    items = [
        {"key": "operating_locations", "label": "Operating locations / states", "weight": 10,
         "done": states_count > 0,
         "fix": "Add your operating locations so state WC rate trends apply to your submission."},
        {"key": "headcount", "label": "Employee headcount", "weight": 6,
         "done": bool(headcount),
         "fix": "Set your employee headcount."},
        {"key": "industry", "label": "Industry / NAICS", "weight": 6,
         "done": bool(industry),
         "fix": "Set your industry (NAICS) to enable peer benchmarking."},
        {"key": "experience_mod", "label": "Experience modification rate (EMR)", "weight": 14,
         "done": experience_mod_present,
         "fix": "Record your current experience mod (EMR) — the single number carriers price WC on."},
        {"key": "claim_typing", "label": "Recordable claim classification", "weight": 10,
         "done": recordable_cases == 0 or untyped_recordables == 0,
         "fix": f"Classify {untyped_recordables} untyped recordable claim(s) (acute vs cumulative-trauma)."},
        {"key": "return_to_work", "label": "Return-to-work outcomes", "weight": 8,
         "done": lost_time_cases == 0 or rtw_resolved > 0 or rtw_avg_days is not None,
         "fix": "Capture return-to-work outcomes on lost-time claims."},
        {"key": "class_codes", "label": "WC class-code exposure", "weight": 8,
         "done": class_count > 0,
         "fix": "Map your payroll to WC class codes."},
        {"key": "epl_questionnaire", "label": "EPL underwriting questionnaire", "weight": 18,
         "done": epl_unknown_count == 0,
         "fix": f"Answer {epl_unknown_count} open EPL underwriting question(s) (pay transparency, biometrics, AI hiring, …)."},
        {"key": "epl_operational", "label": "Anti-harassment policy + signatures", "weight": 10,
         "done": (ah_policy_score or 0) > 0,
         "fix": "Document an anti-harassment / EEO policy and collect employee signatures."},
        {"key": "controls_verified", "label": "Verified risk controls", "weight": 10,
         "done": controls_verified_count > 0,
         "fix": f"Verify your risk controls in Proof of Controls ({controls_unverified_count} unverified)."},
    ]
    score = sum(i["weight"] for i in items if i["done"])
    missing = sorted([i for i in items if not i["done"]], key=lambda i: i["weight"], reverse=True)
    return {
        "score": score,
        "band": readiness_band(score),
        "items": items,
        "top_fixes": [i["fix"] for i in missing[:5]],
        "summary": {"done": sum(1 for i in items if i["done"]), "total": len(items)},
    }


async def compute_readiness(conn, company_id: UUID, *, wc=None, epl=None, controls=None) -> dict:
    """Gather the completeness signals + score. Accepts precomputed wc/epl/controls."""
    if wc is None:
        from ..routes.ir_incidents.analytics import compute_wc_metrics  # lazy: route module
        wc = await compute_wc_metrics(conn, company_id)
    if epl is None:
        epl = await epl_readiness.compute_epl_readiness(conn, company_id)
    if controls is None:
        controls = await controls_evidence.build_register(conn, company_id, epl=epl)

    states = await wc_depth.resolve_company_states(conn, company_id)
    mod = (await wc_depth.latest_mods(conn, [company_id])).get(str(company_id), {}).get("experience_mod")
    class_exp = await wc_depth.class_exposures(conn, company_id)

    cb = wc.get("claim_breakdown") or {}
    rtw = wc.get("rtw") or {}
    factors = epl.get("factors") or []
    epl_unknown = sum(1 for f in factors
                      if f.get("attestation") and (f["attestation"] or {}).get("status") == "unknown")
    ah = next((f for f in factors if f.get("key") == "anti_harassment_policy"), None)
    ctrls = controls.get("controls") or []
    verified = sum(1 for c in ctrls if c.get("verified"))
    unverified = sum(1 for c in ctrls if not c.get("verified") and c.get("status") != "na")

    return evaluate(
        states_count=len(states),
        headcount=wc.get("headcount"),
        industry=wc.get("industry"),
        experience_mod_present=mod is not None,
        recordable_cases=int(wc.get("recordable_cases") or 0),
        untyped_recordables=int(cb.get("unknown") or 0),
        lost_time_cases=int(rtw.get("lost_time_cases") or 0),
        rtw_resolved=int(rtw.get("resolved") or 0),
        rtw_avg_days=rtw.get("avg_days_to_rtw"),
        class_count=len(class_exp),
        epl_unknown_count=epl_unknown,
        ah_policy_score=(ah or {}).get("score") or 0,
        controls_verified_count=verified,
        controls_unverified_count=unverified,
    )
