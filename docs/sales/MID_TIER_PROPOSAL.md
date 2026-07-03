# Matcha Mid Tier — Product & Margin Proposal

> Adding a third tier between **Matcha-lite** and the **full platform**: pure SaaS (no consulting), priced for both direct business sales and broker wholesale.

**TL;DR** — Our margin lever is **model choice + compute shape, not price.** Lite already runs Gemini **Flash** on *event-driven* features, so its compute floor is **under $1/seat/month**. That means a Flash-based Mid tier absorbs the 40% broker discount easily. The only two things that can erode margin are (1) **HRIS/Finch per-connection cost** at low seat counts, and (2) **anything that runs on the Pro model or on a continuous schedule.** Gate those, and the economics are healthy everywhere.

---

## 1. The core insight

There are two cost shapes in the codebase, and they behave completely differently under volume pricing:

| Cost shape | Examples | Behavior at $4–6 wholesale |
|---|---|---|
| **Event-driven** (amortizes) | IR analysis (~9 Flash calls *per incident*), handbook audit (Flash, *per upload*), credential inference (1 Flash call *per job title*) | **Safe.** A 100-seat client files a handful of incidents/mo → cost/seat = pennies. Lite already absorbs this fine. |
| **Continuous / per-tenant** (does NOT amortize) | Compliance per-location cron scans, scheduled research jobs (~900s Gemini), ER deep multi-call analysis, **anything on the Pro model** | **Margin killer.** Runs the same whether a tenant has 10 seats or 1000. A 10-seat broker client at ~$40–60/mo wholesale can't cover scheduled research jobs. |

**Gating rule that writes itself:** Mid tier gets event-driven + CRUD features on **Flash**. The continuous-research and consulting modules stay full-platform — which is also exactly the upsell ladder worth a sales call.

---

## 2. What Lite already includes (corrected scope)

Per `CLAUDE.md`, Lite is fuller than the headline four features. Once paid, Lite enables:

- Incident Reporting copilot + IR insights/analysis
- OSHA 300A logs (1-click)
- Handbook audit
- **Employee records** (CRUD)
- **Progressive discipline workflow**
- CSV drag-and-drop employee add (no HRIS)

So Mid doesn't need much to feel like a real step up.

---

## 3. Recommended Mid tier

**Matcha Mid = Lite + HRIS connect + Credential / License Tracking.** Pure SaaS, no consulting.

### The two adds

- **Credential / License Tracking** (`credential_templates` flag) — **cheap** (1 Flash call per job-title inference, then expiry-cron CRUD). The ideal anchor: high perceived value for the regulated-industry books brokers actually sell (healthcare, trades, transport), and **sticky** — expiry reminders drive recurring engagement = retention. Near-zero variable cost.
- **HRIS (Finch / Gusto)** — the tangible "you've graduated past CSV" signal. The *one* real vendor cost in the bundle (see §6). CSV batch stays on for everyone; the HRIS **connection** is gated.

### Optional second module

- **Accommodations (case-tracking only)** — include the ADA case-tracking + templates, but keep the AI "undue-hardship assessment" in Full (ADA interactive-process is legally sensitive = consulting-adjacent = upsell hook).

---

## 4. The three-rung ladder

| Tier | Includes | Pricing |
|---|---|---|
| **Lite** | IR copilot/insights · OSHA 300A · handbook audit · employee records · discipline · **CSV only** | existing |
| **Mid** ⭐ | everything in Lite **+ HRIS connect + CSV batch + Credential/License tracking** · pure SaaS | **$8–10 direct / $4–6 wholesale** |
| **Full** | everything in Mid **+ ER Copilot · Compliance/jurisdictional · pre-termination · deep accommodations · consulting** | contract |

---

## 5. Matcha-lite price floor

**The AI is nearly free.** Lite runs `gemini-3-flash-preview` everywhere — no Pro fallback — on event-driven features. In-code pricing (`server/app/matcha/services/model_pricing.py`): **Flash = $0.50/M in, $3.00/M out**.

| Lite feature | Model calls | Cost |
|---|---|---|
| IR full analysis (7 calls) + copilot turn | Flash · ~25–35k in / 5–10k out | **~$0.02 / incident** |
| Handbook audit (multi-state) | Flash · ~26k in / 3–5k out | **~$0.016 / audit** |
| OSHA 300A | WeasyPrint only — **zero Gemini** | **$0** |
| Employee records · discipline | no AI | **$0** |

**Per-seat:** even at heavy use (~0.2 incidents/seat/mo + a couple handbook audits/year), variable **AI cost ≈ $0.01–0.05 / seat / month.** Negligible.

So the real floor is **Stripe (~3%) + a sliver of amortized EC2/Postgres infra** (fixed cost already paid across all tiers; the marginal seat ≈ storage):

> **All-in marginal floor ≈ $0.30–0.60 / seat / month** (excluding human support).

**Implication:** The compute floor is under $1. We hold ~85% gross on pure compute down to **~$2–3/seat**. The broker 40% discount is **not** a margin threat on any Flash + event-driven feature.

---

## 6. Mid wholesale unit economics

At $5/seat (midpoint of $4–6 wholesale):

| Line | $/seat/mo |
|---|---|
| Revenue (wholesale mid) | $5.00 |
| Stripe ~3% | −$0.15 |
| AI (Flash, event-driven, heavy) | −$0.05 |
| Infra (amortized) | −$0.10 |
| **Gross before HRIS + support** | **~$4.70 (94%)** |
| **HRIS (Finch, per-tenant)** | **the one variable ↓** |

**Finch is the only line that can flip it.** It's a per-**connection** vendor cost (not in code — our contract), spread over a tenant's seats. At a ~$50/connection/mo example:

- 50 seats → **$1.00/seat**
- 500 seats → **$0.10/seat**
- **10 seats → $5.00/seat → margin gone**

### Two margin guardrails

1. **Seat minimum on wholesale (≥ 25–50 seats)** — so the Finch connection + fixed per-tenant costs amortize. Volume discount should *require* volume.
2. **Gate the HRIS connection behind a headcount floor** (reuse Lite's existing "CSV unless thousands of employees" logic). CSV batch stays default-on for everyone; advertise HRIS as a Mid feature, but don't let a tiny client trigger a Finch bill bigger than their MRR.

> **Action item:** plug our real Finch per-connection rate into the table above — it's the only number not readable from code.

---

## 7. Matcha Werk — personal vs business

Both are **already separate Stripe SKUs**, and the **token cap is what makes each safe.** In-code: **Pro = $2.00/M in, $12.00/M out.**

| | Personal $20/mo | Business $40/mo |
|---|---|---|
| Token grant | 1M/mo (cap = guardrail) | 5M/mo |
| Model | **Pro** (`gemini-3.1-pro-preview`) | Flash default, Pro opt-in |
| Buyer | individual / prosumer, no company | company team |
| Full-burn AI worst case | ~$3–4.50 (1M on Pro) | ~$5.63 (5M on Flash) |
| **Worst-case margin** | **~73–77%** | **~85%** |
| Typical margin | ~88% | ~88% |
| Risk case | — | **Pro + full 5M burn → ~$22.50 → 44%** |

### Recommendation: keep separate, keep both token-metered — do NOT flat-bundle into the HR tiers

- **Personal Werk = standalone prosumer product.** Different buyer (individual, no company) than the HR tiers. Leave as-is; the 1M cap on Pro bounds the downside. Healthy at $20.
- **Business Werk = metered add-on, not a flat bundle.** The 5M-token model works *because* it's capped. Folding all-you-can-eat Werk into a flat $8–10 HR seat exposes us to the Pro-burn case (that 44% row) with **no cap to stop it.** Keep it opt-in metered on any tier.
- **If we want Werk to feel "included" in Mid/Full:** include only the **zero-AI collab layer** (channels + inbox + journals + presence — no Gemini calls) flat, and keep the AI surfaces (threads, projects, recruiting pipeline, payer/compliance modes — all of which can hit Pro + Google grounding) on the metered economy.

---

## 8. Bottom line

- **Margin lever = model + compute-shape, not price.** Flash + event-driven → floor under $1/seat, so Lite and a Flash-based Mid both absorb the 40% broker cut easily.
- **Only two things need a cap or a gate:**
  - **Finch HRIS** (per-connection) → seat minimum + headcount-gated connect.
  - **Werk-on-Pro** → keep token-metered, never flat-bundled.
- **Mid tier = Lite + HRIS + Credential/License tracking** (optionally + Accommodations-lite). Keeps the continuous-research + consulting modules (Compliance, ER Copilot) as the Full-platform upsell.

---

*Cost figures derived from the codebase: model IDs in `server/app/config.py`, pricing in `server/app/matcha/services/model_pricing.py`, IR calls in `server/app/matcha/services/ir_analysis.py` + `ir_ai_orchestrator.py`, OSHA render in `server/app/matcha/routes/ir_incidents/_osha_pdf.py`, handbook audit in `server/app/core/services/handbook_audit_service.py`, Werk token economy in `server/app/matcha/services/token_budget_service.py` + `routes/billing.py`. Finch per-connection rate is a vendor-contract input, not in code.*
