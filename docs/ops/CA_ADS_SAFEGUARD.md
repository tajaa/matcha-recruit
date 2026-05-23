# Matcha & California Automated-Decision-System Rules — Staying Assistive, Not an "Agent"

**Status:** Internal engineering + product guidance. Not legal advice; cites and contract language are confirmed with counsel.
**Owner:** Platform / Compliance. **Last reviewed:** 2026-05-22.

---

## 1. Position

Matcha is an **assistive** compliance and employee-relations platform. It does not make employment decisions and is not designed to operate autonomously. Every output that touches an individual is **advisory** and routed to a human (and, for separations, to counsel) who makes the decision.

Our employment-risk features exist to **protect employees**. They surface a company's *legal exposure* — retaliation, discrimination, wrongful-termination, and documentation risk — **before** the company acts, so the company stays compliant and does not engage in risky or unlawful behavior. We are a safeguard against bad practices, not an engine that selects people for adverse action.

This document ensures no Matcha feature is classified as an Automated-Decision System used to make or substantially facilitate an adverse employment decision, and that Matcha is not deemed an employer's "agent" carrying derivative FEHA liability. Where any feature edges toward that classification, [Section 6](#6-amendment-checklist-when-a-feature-crosses-the-line) is the amendment we make.

---

## 2. The legal trigger we are avoiding

California Civil Rights Council regulations amending the FEHA employment regulations, **effective October 1, 2025**:

- **ADS definition:** "a computational process that makes a decision or facilitates human decisionmaking regarding an employment benefit," using AI / machine-learning / algorithms / statistics or other data-processing techniques.
- **Coverage:** Using an ADS in hiring, firing, promotion, or discipline that discriminates — directly or by disparate impact — on a protected basis is unlawful.
- **Agent / third-party reach:** An employer is responsible for ADS use whether the tool is built in-house or procured; aiding-and-abetting liability can implicate the third party that supplies or operates the tool. A vendor performing a function traditionally performed by the employer can be treated as the employer's **agent**.
- **Recordkeeping:** ADS-related data — inputs, outputs (scores/rankings), selection criteria, and testing results — must be retained for **four years**.
- **Anti-bias testing:** The presence, quality, recency, and results of anti-bias testing are relevant evidence in a discrimination claim; the *absence* of testing is adverse evidence.
- **Medical-inquiry trap:** An ADS that elicits disability or medical information may be an unlawful medical inquiry.
- **On the horizon:** SB 7 ("No Robo Bosses") was vetoed Oct 13 2025; **SB 947** (reintroduced Feb 2 2026) would bar *sole* reliance on an ADS for discipline/termination and require employee notice. We design forward to it.

**Sources:** [CRD final regulation text (PDF)](https://calcivilrights.ca.gov/wp-content/uploads/sites/32/2025/06/Final-Text-regulations-automated-employment-decision-systems.pdf) · CRD approval notice (Jun 27 2025) · law-firm summaries (Ogletree, Jackson Lewis, Paul Hastings). Exact CCR subsection numbers to be pinned by counsel against the final text.

---

## 3. Feature classification

| Feature | Per-person output? | Tied to an employment decision? | Classification | Action |
|---|---|---|---|---|
| **Pre-Termination Check** | Yes (0–100 exposure score + memo) | Adjacent to a separation | **In scope — govern as assistive** | [§4](#4-safeguard-architecture-engineering) safeguards |
| **ER Copilot** | Yes (investigation findings) | Can feed discipline | **Borderline — govern as assistive** | [§4](#4-safeguard-architecture-engineering) safeguards |
| Risk Assessment | No (org-level $-exposure) | No | Out of scope | None |
| Compliance Engine / Legislative Tracker | No | No | Out of scope | None |
| License & Training Tracking | No | No | Out of scope | None |
| Incident Reporting / IR Analysis / OSHA logs | Categorizes *incidents*, not people | No | Out of scope | None |
| Matcha Work (drafting/research/chat) | No | No | Out of scope | None |
| **Flight Risk** | Yes (propensity score per employee) | Highest individual-scoring risk | **Retired — not offered** | Disable + document |

**Key distinction for the two in-scope features:** both assess the **employer's legal exposure** (is this separation retaliatory or biased?), not the employee's merit or fitness. They read protected *activity* and timing in order to **flag and prevent** retaliation — the opposite of selecting against a protected class. [Section 4](#4-safeguard-architecture-engineering) makes that an enforced invariant, not just intent.

---

## 4. Safeguard architecture (engineering)

Applied to Pre-Termination Check and ER Copilot:

- **S1 — Human-in-the-loop hard gate.** Output is advisory only. No endpoint emits a "terminate" / "discipline" decision. Before any assessment is finalized or exported, require an explicit, **audit-logged human acknowledgment** (and, for separations, a counsel-review acknowledgment). This defeats the "sole reliance" prong and front-runs SB 947.
- **S2 — Exposure framing invariant.** Outputs describe the **employer's** litigation / retaliation / bias risk and cite the implicated statutes; they never rank employee worth and never recommend the adverse action. Enforce via prompt guardrails + output validation + tests.
- **S3 — No protected-class scoring.** Scoring inputs are limited to protected *activity*, leave status, documentation completeness, and timing — used to flag retaliation risk and protect the employee. Protected **characteristics** (race, sex, age, disability, etc.) are excluded from scoring inputs. Document the dimension list; assert exclusion in code + tests.
- **S4 — No medical inquiry.** No feature elicits disability/medical information as a scoring input.
- **S5 — Four-year retention.** Retain inputs, score/band, criteria, generated memo, and the human-signoff record for ≥ 4 years. Exclude these tables from any sub-4-year pruning/cleanup job.
- **S6 — Bias testing, documented.** Run periodic anti-bias evaluation of the scoring logic; store results as a retrievable artifact. Because outputs are employer-exposure (not selection), include the disparate-impact analysis showing no protected-class scoring.
- **S7 — Transparency / notice readiness.** Be able to generate an employee-facing notice and the human-decision record on demand (forward-compatible with SB 947).

---

## 5. Contractual safeguards (MSA / DPA — with counsel)

- Define Matcha as **assistive tooling**; the employer is the sole decision-maker and "covered entity."
- Employer-obligations clause: human review of any individual output, the employer's own 4-year recordkeeping, and lawful-use representations.
- Vendor warranties: anti-bias testing performed; data-use limits; **no protected-class scoring**.
- Liability allocation / indemnification for employer misuse (e.g., relying solely on an output).
- Right-to-audit / provide testing protocols to support employer due diligence.

---

## 6. Amendment checklist (when a feature crosses the line)

1. Convert any actionable adverse *recommendation* into an exposure-only assessment + counsel referral.
2. Add the audit-logged human-signoff gate (S1).
3. Strip any protected-characteristic input from scoring (S3).
4. Confirm 4-year retention; disable sub-4-year pruning (S5).
5. Add/refresh the bias-test job and store the report (S6).
6. Re-classify the feature in the [Section 3](#3-feature-classification) table and date the change.

---

## 7. Code touchpoints (implementation map — future work)

- `server/app/matcha/services/pre_termination_service.py` — exposure-framing invariant, prompt guardrail, signoff gate, retention. (Already cites Title VII §704(a), FMLA, OSHA 11(c) and disclaims "not legal advice" — formalize as invariants + tests.)
- `server/app/matcha/routes/er_copilot.py` — determination flow human-gate, retention.
- Retention/cleanup jobs (`server/app/workers/tasks/*`) — exclude pre-termination + ER determination tables from < 4-yr pruning.
- `server/app/matcha/services/flight_risk_service.py` — feature-flag off; ensure not surfaced in any client UI.
- Contract templates — out of repo, with counsel.

---

## 8. Verification

- Tests: no endpoint returns a fire/discipline decision; protected characteristics absent from scoring inputs; retention ≥ 4 yr enforced; human-signoff required before finalize/export.
- Manual: run a Pre-Termination assessment → confirm output is exposure-framed, carries the counsel disclaimer, and blocks finalize until signoff is logged.
