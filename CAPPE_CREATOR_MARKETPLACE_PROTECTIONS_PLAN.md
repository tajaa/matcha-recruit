# Creator-first protections + deal-review tooling → CAPPE_CREATOR_MARKETPLACE_PLAN.md

## Context

User direction: "make sure this also has tooling for the creators to review their deals and
we have infrastructure that protects influencers when brands are structuring deals — we are
there to help creators more than we are to help brands."

The deliverable is a set of edits to the existing transcription-level spec
`CAPPE_CREATOR_MARKETPLACE_PLAN.md` (repo root). No code is written yet — the spec is what
gets implemented later. All grounding (cappe conventions, Stripe direct-charge pattern,
settings table, admin surface) already done this session; additions below reuse only
already-specced infra (`cappe_marketplace_settings`, `services/collab.py`, `_offer_detail`,
`ui.ts` atoms).

One edit already applied to the main spec: the "Locked decisions" header now names the
creator-first stance. Remaining edits, to be folded into `CAPPE_CREATOR_MARKETPLACE_PLAN.md`:

## A. Structural guardrails — brands cannot send exploitative terms (server-enforced)

Edit **Part 2, `CollabTerms`** validators (models/collab.py spec):

1. **Paid usage must be time-bound**: `usage_rights.scope='paid'` requires
   `duration_months` NOT NULL, max 24. Perpetual paid usage rights are structurally
   impossible. (Organic scope may stay unbounded — that's normal.)
2. **Whitelisting ⇒ paid scope**: `whitelisting=True` only valid when `scope='paid'`
   (running ads from the creator's handle IS paid usage).
3. **Exclusivity must be paid + bounded**: `exclusivity` requires
   `compensation_cents > 0` (no gifting-only category lockouts); `duration_months`
   cap tightened 60 → **12**.
4. **FTC disclosure is non-waivable**: validator rejects `ftc_disclosure=False` with
   "FTC disclosure cannot be waived". Field stays in the schema for stability; frontend
   renders it as a static "always on" line, not a checkbox.
5. Note added: all three payment schedules already pay-as-you-go or better by design —
   there is deliberately no "100% on completion" or net-X schedule a brand could pick.

## B. Cancel asymmetry — brand owes for approved work (edit Part 3 `cancel_offer`)

- `cancelled_by='creator'` → all unpaid payments (`scheduled/due/processing`) → `cancelled`
  (creator walks away, forfeits unearned installments).
- `cancelled_by='brand'`:
  - offer was `active` (work started): payments already `due`/`processing` **survive** —
    due-ness fires on approval events, so due == earned; only `scheduled` rows cancel.
  - offer was `accepted` (never funded, no work possible): everything unpaid cancels.
- Consequence edit in **Part 4.3 checkout endpoint**: allow checkout when offer status in
  `('active','cancelled')` so surviving due rows on a brand-cancelled offer remain payable.
- Frontend cancel dialog copy differs by side (brand warned: "you still owe for approved
  deliverables").

## C. Auto-approve on brand silence (protects creator payout)

- New settings seed row in **Part 1 migration**: `('auto_approve_days', '{"days": 14}')`.
- New **Part 3** function `auto_approve_overdue(conn, offer_id)`: for `active` offers,
  `UPDATE cappe_collab_deliverables SET status='approved', approved_at=NOW(),
  review_note='Auto-approved after N days without brand review' WHERE offer_id=$1 AND
  status='submitted' AND submitted_at < NOW() - make_interval(days => $N)`; then the same
  fire-payments + completion chain as manual approve. Evaluated **lazily at read time**
  (top of `_offer_detail` and offer-list fetch) — no new worker infra; the creator opening
  their deal is the trigger. Emails: brand gets payment-due, creator gets approved notice.
- UI: submitted deliverables show "Auto-approves {date}" countdown (both sides — reassurance
  for creator, pressure on brand).

## D. Deal Check — deterministic creator-side deal review tooling (the "review their deals" ask)

New **Part 3** pure function
`analyze_terms_for_creator(terms, rate_rows, brand_stats, now) -> list[DealCheckItem]`
(`DealCheckItem = {key, severity: 'good'|'caution'|'warning', title, detail}`) — no LLM,
mirrors the discipline module's deterministic-gate philosophy. Rules with exact thresholds:

| key | severity | trigger |
|---|---|---|
| `rate_below_card` | warning | creator's rate-card sum for matching type+platform deliverables > compensation (partial card coverage → caution with partial estimate) |
| `paid_usage_long` | caution 6–12mo / warning >12mo | paid usage duration |
| `whitelisting_unpriced` | caution | whitelisting=true — "typically priced 30–100% above base rate" |
| `exclusivity_low_pay` | warning | compensation ÷ exclusivity months < $250/mo |
| `high_revision_rounds` | caution | revision_rounds ≥ 3 |
| `tight_deadlines` | caution | any due_date < 7 days out |
| `no_upfront_money` | caution | schedule = per_deliverable — "nothing until first approval; consider countering 50/50 or upfront" |
| `heavy_scope_low_total` | warning | ≥5 deliverables AND comp/deliverable < $100 |
| `new_brand` | caution | brand has 0 completed collabs |
| `payments_protected` | good | always — payments run through Gummfit checkout, terms lock at accept |

Computed server-side, returned in `OfferDetail.deal_check` **only when `side='creator'`**
(brand never receives the creator's private analysis). New Pydantic `DealCheckItem` +
optional `deal_check` field in **Part 2** response models.

## E. Brand track record — transparency for the creator (edit Part 2 + 4.3)

New `BrandStats` model + `OfferDetail.brand_stats` (creator side only): SQL over
`cappe_collab_offers`/`cappe_collab_payments` for that brand —
`completed_collabs`, `brand_cancelled`, `in_progress`, `avg_hours_to_pay` (paid_at − due_at).
Zero history renders "New brand — first collab on Gummfit".

## F. Payment nudge (creator chases an overdue installment)

New endpoint **Part 4.3**: `POST /collab/offers/{id}/payments/{pid}/nudge` — creator-only,
payment status `due`/`processing`, rate-limited 1/day per payment
(`check_rate_limit(f"nudge:{pid}", ...)`), re-sends `send_cappe_collab_payment_due_email`
to the brand. UI: "Remind brand" button on due rows >3 days old; overdue badge styling
from `due_at` age (UI-computed).

## G. Frontend additions (edit Part 7)

- **`DealCheckCard.tsx`** component: rendered top of creator-side OfferDetail term panel —
  severity-grouped list (warning red-ish/amber cards, cautions amber, goods emerald),
  headline count ("2 things to review before accepting").
- **Brand stats strip** on creator-side OfferDetail header.
- Funding banner: status `accepted` + unpaid on_accept → creator sees "Wait for funding
  before starting work — the brand hasn't paid the first installment yet".
- SendOfferSheet: paid-usage duration input becomes required when scope=paid (max 24),
  exclusivity months max 12, FTC checkbox → static always-on line.
- Auto-approve countdown on submitted deliverables; nudge button on due payments.
- CreatorsLanding gains a "Creator-first protections" section (4 bullets mirroring Part 9B).

## H. Admin oversight (edit Part 8)

Collabs tab gains a per-brand table (offers sent, completed, brand-cancel count/rate,
avg hours-to-pay) so we can spot abusive brands early. Brand offer-privilege suspension
itself → deferred list.

## I. Bookkeeping edits

- **Part 9** state machine: auto-approve transition + cancel asymmetry noted.
- New **Part 9B — Creator-first protections summary**: one table of every protection +
  where enforced + tunable constants (`auto_approve_days` admin-tunable; Deal Check
  thresholds = documented constants in `services/collab.py`).
- **Part 10 deferred** adds: kill fees, formal dispute flow, brand offer-privilege
  suspension, AI deal explainer on top of Deal Check, Deal-Check thresholds as admin
  settings.
- **Part 11 build order**: Deal Check + protections land with step 5 (collab routes);
  e2e script extended with an auto-approve + brand-cancel case.

## Verification (of the spec edit itself)

Re-read edited doc for internal consistency: validators in Part 2 match Deal Check rules in
Part 3, cancel rules consistent across Parts 3/4.3/9/9B, settings keys consistent across
Parts 1/3/6/8. No code runs at this stage.
