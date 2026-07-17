"""What being out of compliance actually costs you, beyond the fine.

A dollar range answers "how big is the check". It does not answer the questions
that decide whether an obligation matters:

  * **insurability** — will any policy absorb this? Statutory fines and penalties
    are generally uninsurable as a matter of public policy, so a compliance gap
    is untransferred exposure sitting on the company's own balance sheet. This is
    the BROKER's question, and nothing in the product answered it: the broker's
    compliance signal was a row-count, and the submission packet had no
    compliance section at all.
  * **private right of action** — often the real number. California PAGA
    routinely dwarfs the statutory penalty it derives from, and unlike the fine
    it is EPLI-adjacent, so it bridges to the insurance stack.
  * **detection mode** — a statutory ceiling is not an expected loss. A wage
    violation is visible on every paycheck and gets found; a training gap
    surfaces only once someone sues.
  * **escalation / cure** — OSHA willful is 10x, and many obligations can be
    cured before the penalty attaches. This is what orders the fix list.

⚠️  PARTIAL TABLE — deliberately incomplete, exactly like
``risk_transfer._STATE_ANTI_INDEMNITY`` and
``discipline_compliance._STATE_SICK_LEAVE_PROTECTIONS``. Every row below was
individually cited. Keys we have not sourced are ABSENT, and an absent key
degrades to ``review`` — never to "no exposure". Do NOT add rows by inference
from a neighbouring statute, from the key's name, or from memory: a wrong row
produces a confident wrong verdict in something a broker hands an underwriter.

To extend: read the cited authority, then add the row with its citation. The
resolver is keyed on ``regulation_key`` (the curated RKD vocabulary), because
these facts are properties of the OBLIGATION, not of the jurisdiction row that
happens to state its dollar figure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

# ── vocabularies ────────────────────────────────────────────────────────────

# uninsurable_fine — a statutory fine/penalty; public policy bars insuring it.
# insurable        — the exposure is ordinary civil liability a policy can absorb.
# partial          — the fine is uninsurable but it drags insurable liability
#                    behind it (defense costs, private suits, back pay).
# review           — not sourced. The honest default. NEVER means "no exposure".
Insurability = Literal["uninsurable_fine", "insurable", "partial", "review"]

# automatic  — visible in records an auditor/employee can read without a dispute
#              (a paycheck, a posting, a log). Assume it will be found.
# complaint  — surfaces when someone reports it.
# audit      — surfaces on a scheduled or random regulator inspection.
# litigation — typically surfaces only once a claim is filed.
# review     — not sourced.
DetectionMode = Literal["automatic", "complaint", "audit", "litigation", "review"]


@dataclass(frozen=True)
class RiskDims:
    insurability: Insurability = "review"
    insurability_note: Optional[str] = None
    private_right_of_action: Optional[bool] = None
    private_right_note: Optional[str] = None
    detection_mode: DetectionMode = "review"
    detection_note: Optional[str] = None
    escalation_note: Optional[str] = None
    cure_period: Optional[bool] = None
    cure_note: Optional[str] = None
    citations: List[str] = field(default_factory=list)

    @property
    def sourced(self) -> bool:
        """False = we have not researched this key; the values are defaults."""
        return bool(self.citations)


_REVIEW = RiskDims()


# ── the curated table ───────────────────────────────────────────────────────

_DIMS: Dict[str, RiskDims] = {
    # ---- wage & hour ------------------------------------------------------
    "state_minimum_wage": RiskDims(
        insurability="uninsurable_fine",
        insurability_note=(
            "Unpaid wages and statutory penalties are not insurable losses; EPLI "
            "forms customarily exclude wage-and-hour liability, and back pay is "
            "restitution of money already owed."
        ),
        private_right_of_action=True,
        private_right_note=(
            "FLSA s216(b) permits employee suits for unpaid wages plus an equal "
            "amount as liquidated damages, costs and attorney's fees. In "
            "California, PAGA (Lab. Code s2699) lets an aggrieved employee "
            "recover civil penalties per employee per pay period — routinely "
            "larger than the underlying wage claim."
        ),
        detection_mode="automatic",
        detection_note="Every paycheck evidences the rate; visible to any audit or employee.",
        escalation_note=(
            "FLSA s216(a): willful violations carry criminal fines up to $10,000; "
            "a willful violation also extends the limitations period from 2 to 3 "
            "years (s255(a))."
        ),
        cure_period=False,
        cure_note="Paying the shortfall later does not extinguish liquidated damages.",
        citations=[
            "29 U.S.C. 216",
            "29 U.S.C. 255(a)",
            "Cal. Lab. Code 2699",
        ],
    ),
    "local_minimum_wage": RiskDims(
        insurability="uninsurable_fine",
        insurability_note="Same as the state floor: unpaid wages are restitution, not an insurable loss.",
        private_right_of_action=True,
        private_right_note="Most local wage ordinances create a private right of action; many add their own penalties on top of the state scheme.",
        detection_mode="automatic",
        detection_note="Evidenced on every paycheck.",
        cure_period=False,
        citations=["29 U.S.C. 216"],
    ),
    "national_minimum_wage": RiskDims(
        insurability="uninsurable_fine",
        insurability_note="Back wages are restitution; EPLI wage-and-hour exclusions are customary.",
        private_right_of_action=True,
        private_right_note="FLSA s216(b): unpaid wages plus liquidated damages, costs and fees.",
        detection_mode="automatic",
        escalation_note="Willful violations: criminal fines up to $10,000 (29 U.S.C. 216(a)); 3-year limitations period (s255(a)).",
        cure_period=False,
        citations=["29 U.S.C. 216", "29 U.S.C. 255(a)"],
    ),
    "exempt_salary_threshold": RiskDims(
        insurability="uninsurable_fine",
        insurability_note="A misclassification finding produces owed overtime — restitution, and squarely inside the customary EPLI wage-and-hour exclusion.",
        private_right_of_action=True,
        private_right_note=(
            "Misclassification is the classic FLSA collective action: one "
            "misclassified role usually implicates everyone in it, so exposure "
            "scales with headcount rather than with the individual."
        ),
        detection_mode="automatic",
        detection_note="Salary and duties are documented in payroll and the job description.",
        escalation_note="Willful: 3-year lookback rather than 2 (29 U.S.C. 255(a)).",
        cure_period=False,
        citations=["29 C.F.R. 541.600", "29 U.S.C. 216", "29 U.S.C. 255(a)"],
    ),

    # ---- workplace safety --------------------------------------------------
    "osha_general_duty": RiskDims(
        insurability="uninsurable_fine",
        insurability_note=(
            "OSHA civil penalties are fines and are not insurable. The injury "
            "that prompted the citation is a workers'-comp matter — the "
            "citation itself is not."
        ),
        private_right_of_action=False,
        private_right_note=(
            "The OSH Act creates no private right of action; enforcement runs "
            "through the Secretary. A citation is still admissible evidence of "
            "the standard of care in third-party litigation."
        ),
        detection_mode="audit",
        detection_note="Surfaces on inspection — which a serious injury or an employee complaint triggers.",
        escalation_note=(
            "29 U.S.C. 666: willful or repeated violations up to $165,514 per "
            "violation vs $16,550 for serious — roughly a 10x multiplier. A "
            "willful violation causing death carries criminal exposure."
        ),
        cure_period=True,
        cure_note="Abatement within the cited period avoids the failure-to-abate daily penalty (29 U.S.C. 666(d)).",
        citations=["29 U.S.C. 654(a)(1)", "29 U.S.C. 666"],
    ),
    "injury_illness_recordkeeping": RiskDims(
        insurability="uninsurable_fine",
        insurability_note="A recordkeeping citation is a civil fine — uninsurable.",
        private_right_of_action=False,
        detection_mode="audit",
        detection_note="The 300 log is the first thing an inspection asks for; the ITA submission is machine-checkable.",
        escalation_note="29 C.F.R. 1904.4 requires recording within 7 calendar days; s1904.39 requires reporting a fatality within 8 hours and an amputation/hospitalisation within 24. Missing those windows is its own violation.",
        cure_period=False,
        cure_note="A late record does not undo a missed reporting window.",
        citations=["29 C.F.R. 1904.4", "29 C.F.R. 1904.39", "29 U.S.C. 666"],
    ),
    "lockout_tagout": RiskDims(
        insurability="uninsurable_fine",
        insurability_note="OSHA penalty, uninsurable. The underlying injury is a WC loss that also drives the experience mod.",
        private_right_of_action=False,
        detection_mode="audit",
        detection_note="Among OSHA's most-cited standards; an energy-control incident guarantees an inspection.",
        escalation_note="Willful/repeat up to $165,514 per violation (29 U.S.C. 666).",
        cure_period=True,
        cure_note="Abatement stops the daily failure-to-abate penalty.",
        citations=["29 C.F.R. 1910.147", "29 U.S.C. 666"],
    ),
    "hazard_communication": RiskDims(
        insurability="uninsurable_fine",
        insurability_note=(
            "An OSHA citation is a civil fine and is not insurable. A chemical "
            "exposure arising from the same failure is a WC/liability loss — the "
            "citation is not."
        ),
        private_right_of_action=False,
        private_right_note="The OSH Act creates no private right of action; a citation is still evidence of the standard of care.",
        detection_mode="audit",
        detection_note="SDS availability and labelling are checked on any general-industry inspection.",
        escalation_note="Willful/repeat up to $165,514 per violation (29 U.S.C. 666).",
        cure_period=True,
        cure_note="Abatement within the cited period avoids the failure-to-abate daily penalty.",
        citations=["29 C.F.R. 1910.1200", "29 U.S.C. 666"],
    ),

    # ---- anti-discrimination ----------------------------------------------
    "harassment_prevention_training": RiskDims(
        insurability="partial",
        insurability_note=(
            "The training mandate itself is not an insurable loss, but the "
            "harassment claim it exists to prevent is the core EPLI exposure — "
            "and a training gap is what plaintiff's counsel uses to defeat the "
            "employer's affirmative defense. This is the clearest case where a "
            "compliance gap raises an INSURED loss rather than an uninsured one."
        ),
        private_right_of_action=True,
        private_right_note=(
            "No direct private action for failing to train, but under "
            "Faragher/Ellerth the employer's preventive-care showing is an "
            "element of its defense to a hostile-environment claim."
        ),
        detection_mode="litigation",
        detection_note="Rarely audited; surfaces in discovery once a claim is filed.",
        cure_period=True,
        cure_note="Training completed before a claim preserves the defense; after does not.",
        citations=[
            "Cal. Gov. Code 12950.1",
            "Faragher v. City of Boca Raton, 524 U.S. 775 (1998)",
            "Burlington Indus. v. Ellerth, 524 U.S. 742 (1998)",
        ],
    ),
}


# ── resolver ────────────────────────────────────────────────────────────────

def risk_dims_for(regulation_key: Optional[str]) -> RiskDims:
    """Dimensions for an obligation. Unsourced keys degrade to `review`.

    Never raises and never guesses — an unmapped key returns the review default,
    whose `sourced` is False, so a caller can render "needs review" instead of
    implying we checked and found nothing.
    """
    if not regulation_key:
        return _REVIEW
    return _DIMS.get(regulation_key, _REVIEW)


def is_uninsurable(regulation_key: Optional[str]) -> bool:
    """Only a SOURCED uninsurable verdict counts.

    `review` must not fall into this bucket: quietly counting unsourced keys as
    uninsurable would inflate the one number a broker takes to an underwriter.
    """
    d = risk_dims_for(regulation_key)
    return d.sourced and d.insurability == "uninsurable_fine"


def sourced_keys() -> List[str]:
    return sorted(_DIMS)


def dims_payload(regulation_key: Optional[str]) -> dict:
    """Wire shape for the API. `sourced` travels so the UI can say "needs review"
    rather than presenting a default as a finding."""
    d = risk_dims_for(regulation_key)
    return {
        "sourced": d.sourced,
        "insurability": d.insurability,
        "insurability_note": d.insurability_note,
        "private_right_of_action": d.private_right_of_action,
        "private_right_note": d.private_right_note,
        "detection_mode": d.detection_mode,
        "detection_note": d.detection_note,
        "escalation_note": d.escalation_note,
        "cure_period": d.cure_period,
        "cure_note": d.cure_note,
        "citations": list(d.citations),
    }
