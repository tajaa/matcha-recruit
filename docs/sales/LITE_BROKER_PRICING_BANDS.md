# Matcha-Lite Brokerage Pricing Model & Unit Economics

## 1. Underlying Cost Basis (Unit Economics)

To establish defensible wholesale pricing for large brokerages, we must first isolate our variable costs to serve an employee.

### AI Processing Costs (Gemini 3.0 Flash)
Matcha relies heavily on Gemini 3.0 Flash (`gemini-3-flash-preview`), priced at $0.50 per 1M input tokens and $3.00 per 1M output tokens.

*   **Incident Processing:** Auto-categorization, severity assessment, OSHA privacy cleansing, and the Copilot orchestration require approximately 6-8 API calls per incident.
    *   *Average token usage:* 25k input / 3k output.
    *   *Cost per incident:* **~$0.03**
*   **Voice Intake (Add-on):** Multimodal audio parsing using Gemini.
    *   *Cost per voice incident:* **~$0.005**
*   **Compliance Audit & Resource Hub:** 
    *   *Cost per audit generation/resource:* **~$0.01** (amortized to zero on a per-month basis)

**Estimated Core AI Cost per Employee:** Assuming an industry-average 15 incidents per 100 FTEs annually, the AI cost translates to **$0.0004 Per Employee Per Month (PEPM)**. AI costs are a negligible factor in our floor pricing.

### Third-Party Vendor Costs (HRIS)
*   **Finch (HRIS Integration):** Finch charges based on connected lives. At high enterprise volumes, this typically scales down to a hard cost of **$0.20 - $0.30 PEPM**.

---

## 2. Matcha-Lite Core Pricing (Base Platform)

Retail pricing for Matcha-Lite is currently **$10.00 PEPM** (sold in blocks of 10 for $100/mo). For large brokerages using this to win/retain benefits Broker of Record (BOR) status, we offer aggressive wholesale discounting.

*Our core variable cost (AI + Hosting) is <$0.02 PEPM, yielding >95% gross margins on the base platform.*

| Headcount Band | Suggested Wholesale PEPM | Monthly Rev at Tier Floor | Annual Rev at Tier Floor |
| :--- | :--- | :--- | :--- |
| **1,000 - 10,000** | **$2.00** | $2,000 | $24,000 |
| **10,000 - 50,000** | **$1.25** | $12,500 | $150,000 |
| **50,000 - 100,000** | **$0.75** | $37,500 | $450,000 |
| **100,000 - 500,000** | **$0.40** | $40,000 | $480,000 |

*Note: Brokerages will typically bundle this into their PEPM advisory fee to their clients, or absorb the cost directly as a client retention expense.*

---

## 3. Add-On Pricing Strategy

We isolate high-cost or high-value features as modular add-ons. This protects our margins from Finch's hard costs and allows us to capture upside on Voice.

### Add-on 1: Automated HRIS Sync (powered by Finch)
Allows employers to automatically sync employee directories, org charts, and payroll data into Matcha.
*   **Vendor Cost:** ~$0.25 PEPM
*   **Suggested Price:** **+$0.50 PEPM** (Flat across all bands)
*   **Margin:** ~50%
*   *Sales Narrative:* "Eliminates manual roster uploads and ensures incident reports are automatically tied to the correct, active employee record."

### Add-on 2: Voice Incident Intake & OSHA Logs
Enables frontline workers to "talk in" an incident report from their phone. Includes automatic transcription, AI extraction to the OSHA 300 log format, and privacy-masking.
*   **Vendor Cost (Gemini Audio):** <$0.01 PEPM
*   **Suggested Price:** **+$0.35 PEPM**
*   **Margin:** >95%
*   *Sales Narrative:* "Dramatically increases safety reporting compliance in deskless workforces (manufacturing, construction, hospitality) by removing the friction of typing out forms."

---

## 4. Total Expected Yield (Base + Add-ons)

If a brokerage purchases the base platform and opts into both add-ons (HRIS + Voice = +$0.85 PEPM), the blended economics look like this:

| Headcount Band | Fully Loaded PEPM (w/ Add-ons) | Total Monthly Rev (at floor) | Blended Gross Margin |
| :--- | :--- | :--- | :--- |
| **1k - 10k** | **$2.85** | $2,850 | ~90% |
| **10k - 50k** | **$2.10** | $21,000 | ~86% |
| **50k - 100k** | **$1.60** | $80,000 | ~82% |
| **100k - 500k** | **$1.25** | $125,000 | ~77% |
