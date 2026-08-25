-- /admin/updates changelog rows for the customer-facing releases merged
-- 2026-08-22 through 2026-08-24 (PRs #239, #244, #254, #256, #257).
-- Idempotent: deletes each id first, then inserts below the current minimum
-- position so the newest row remains at the top without assuming positions
-- are zero-based or contiguous.
-- Run against dev AND prod.

BEGIN;

DELETE FROM admin_updates WHERE id IN (
  'pr-239-feat-schedule-use-huume-assistant-surface',
  'pr-244-feat-tellus-add-shoutout-radar',
  'pr-254-feat-tellus-ship-shoutout-offer-redemption',
  'pr-256-feat-inventory-waste-shrinkage-phase-1',
  'pr-257-feat-inventory-forecast-insights-waste-rollup'
);

WITH base AS (
  SELECT COALESCE(MIN(position), 0) - 5 AS top
  FROM admin_updates
),
new_rows (id, offset_from_top, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) AS (
  VALUES
  (
    'pr-257-feat-inventory-forecast-insights-waste-rollup',
    0,
    '2026-08-24'::date,
    'Matcha Work',
    'Inventory forecast and waste insights — deterministic conclusions, PAR guidance, and one control hub',
    'Turns the inventory forecast and waste surfaces into a manager-facing control loop: POS setup lives in the Inventory Hub, reorder plans lead with deterministic urgency and cost conclusions, waste analysis compares periods and explains the biggest drivers, and PAR changes stay behind explicit guardrails and review.',
    '["POS connection setup now lives in the Inventory Hub, beside the catalog and sales controls, instead of being split across the forecast page.", "Forecast pages lead with an actionable reorder plan: urgency buckets, runout dates, lead demand, estimated order value, suppressed items, and a one-click path to stage an order.", "Forecast runs now surface a deterministic insight before optional Luna narration, with rate-limited insight endpoints and a refresh path that rechecks the plan and PAR preview.", "PAR drift preview shows which lines are eligible, why others are blocked, and requires an explicit manager action to right-size eligible PARs.", "Waste pages lead with period-over-period conclusions, at-risk items, lot and expiry context, and clearer dollar or units-share attribution when unit cost is unavailable."]'::jsonb,
    '["Work -> Inventory -> Hub: connect Square and map sales data alongside the inventory controls.", "Work -> Inventory -> Forecast: review the reorder plan, suppressed lines, PAR drift preview, and deterministic insight; use Recalculate after changing settings or scenario inputs.", "Work -> Inventory -> Waste: review the conclusion, at-risk items, period comparison, and reason/item breakdown before recording waste or staging an order."]'::jsonb,
    NULL,
    '["Forecast suggestions remain advisory: staging an order and applying eligible PARs are separate, explicit manager actions.", "Luna narration is optional and grounded in the deterministic plan; it does not replace the underlying calculations.", "Items without enough history, a usable count, or required cost data remain visibly suppressed or labeled as estimates rather than being presented as precise recommendations."]'::jsonb,
    'new'
  ),
  (
    'pr-256-feat-inventory-waste-shrinkage-phase-1',
    1,
    '2026-08-24'::date,
    'Matcha Work',
    'Inventory waste and shrinkage — reason-coded waste ledger and grounded capture',
    'Adds a first-class waste movement to Inventory with a controlled reason taxonomy, dollarized rollups, item metadata for later perishability analysis, and a grounded @huume capture path. Waste is tracked as a deduction and is kept out of demand-rate calculations while still being reported beside reorder suggestions.',
    '["New waste movement kind with reason codes for spoilage, expired stock, prep error, overproduction, breakage, contamination, theft, comp, recall, and unknown.", "Waste rollups show units, value, and reason/item breakdowns; reorder suggestions exclude waste from demand but report waste in the window.", "Inventory items can carry category, shelf-life, and yield metadata for more accurate downstream par and usage analysis.", "@huume can capture waste only for an existing matched item; it never auto-creates inventory, and a chat-reported theft is coerced to unknown rather than creating a personnel accusation.", "Estimated waste amendments now correct the stock deduction sign instead of adding inventory back."]'::jsonb,
    '["Enable Inventory, then enable Inventory Waste in the company feature controls.", "Work -> Inventory -> Waste: record a waste movement and choose the reason code, then review the rollup and variance views.", "In a Matcha Work channel, use @huume to describe waste for an existing inventory item and confirm the captured movement."]'::jsonb,
    '["Apply migration invwaste01_inventory_waste.", "The inventory_waste feature requires inventory; it is off by default and should be enabled per company."]'::jsonb,
    '["Waste capture is a ledger entry, not an automatic order or replenishment action.", "The theft safeguard intentionally stores unknown when the only source is a chat aside; managers can correct the reason in the reviewed movement flow."]'::jsonb,
    'action-needed'
  ),
  (
    'pr-254-feat-tellus-ship-shoutout-offer-redemption',
    2,
    '2026-08-24'::date,
    'Marketing',
    'Tell-Us Shoutout offers — approve, send, and redeem store-bound rewards',
    'Completes the Tell-Us shoutout workflow with manual brand approval, store-bound promo offers, public preview and claim links, short-code redemption, revocation, audit coverage, and matching web/iOS claim surfaces.',
    '["Brands can approve a reviewed shoutout mention and mint a single-store offer with an expiry, then copy the link for manual delivery.", "Public preview and claim routes support link claims, while short-code preview and redemption support in-store entry.", "Brands can revoke offers and see the offer lifecycle in the shoutout workspace; offer actions are recorded in the admin audit trail.", "Tell-Us web and iOS clients support offer deep links, claim UI, and normalized short-code entry."]'::jsonb,
    '["Tell-Us brand -> Shoutouts: review a mention, approve it, select the store, and copy the generated offer link.", "Consumers: open the offer link or enter its short code in Tell-Us, then redeem at the participating store.", "Use the brand shoutout view to inspect or revoke an outstanding offer."]'::jsonb,
    '["Apply migrations tellus_app_32_shoutout_offers through tellus_app_37_shoutout_mention_image.", "The offer is manually delivered: approval never sends customer messages or grants a reward automatically."]'::jsonb,
    '["Offers are store-bound and rate-limited; expired or revoked offers cannot be claimed.", "iOS deep links require the shipped associated-domain configuration; the web claim path remains available independently."]'::jsonb,
    'action-needed'
  ),
  (
    'pr-244-feat-tellus-add-shoutout-radar',
    3,
    '2026-08-23'::date,
    'Marketing',
    'Tell-Us Shoutout Radar — grounded mention detection with review queue and scan history',
    'Adds a default-disabled shoutout radar that scans configured social handles for brand mentions, corroborates candidates with Gemini Google Search grounding, deduplicates and confidence-scores results, and gives brands a review queue plus scan history.',
    '["Brands can configure handles and brand terms for scheduled or manual scans.", "Mention candidates use strict URL corroboration, fingerprint deduplication, and confidence scoring instead of being accepted from a single unverified hit.", "A review queue supports approve or reject decisions, with scan runs, duplicate counts, failures, and diagnostics retained for inspection.", "The scheduled worker is pool-free and spend-capped so a scan cannot fan out unbounded model or search calls."]'::jsonb,
    '["Tell-Us brand -> Shoutouts: configure the brand handles and terms, enable the radar, and start a scan.", "Review pending mentions, inspect their corroborating links and confidence, then approve or reject them; use scan history to diagnose a run."]'::jsonb,
    '["Apply migration tellus_app_31_shoutout_radar.", "Set SERP_API_KEY for grounded scans and keep the radar disabled until a brand has configured its handles and terms."]'::jsonb,
    '["The radar is intentionally human-in-the-loop: detection never publishes a mention or grants an offer by itself.", "Offer minting and redemption are described in the follow-on Shoutout Offers update."]'::jsonb,
    'action-needed'
  ),
  (
    'pr-239-feat-schedule-use-huume-assistant-surface',
    4,
    '2026-08-22'::date,
    'Employee Scheduling',
    'Huume schedule assistant — location-aware schedule chat, staged actions, and compliance digests',
    'Brings the Huume assistant into the Schedule Editor and Matcha Work with location-scoped sessions, staged schedule actions that use the canonical confirmation harness, and scheduled compliance-digest delivery.',
    '["Schedule Editor now has a Huume panel that understands the selected location, week, roster, and schedule context.", "Assistant sessions persist across visits and route through the same schedule action envelope used by Matcha Work threads.", "Schedule changes are staged as reviewable action cards and require an explicit confirmation before they write.", "Compliance actions and digest delivery are wired through the scheduling worker so managers can review issues without opening every shift one by one."]'::jsonb,
    '["Enable Employee Scheduling, then open Employees -> Schedule and use the Huume assistant panel.", "Ask for a schedule change or compliance check, review the staged action and affected location/week, and confirm only when it is correct.", "The same assistant surface is available from the relevant Matcha Work schedule thread when the company has the required Work access."]'::jsonb,
    '["Apply migration huumesched01_schedule_assistant_sessions.", "Employee Scheduling remains a per-company feature and requires the Matcha Ops surface; existing schedule eligibility, conflict, and compliance gates still apply."]'::jsonb,
    '["Huume never silently executes a schedule write from a draft turn; confirmation is a separate step and re-checks authorization and current schedule state.", "A session is location-scoped so one site cannot accidentally receive another site''s schedule context."]'::jsonb,
    'action-needed'
  )
)
INSERT INTO admin_updates (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag)
SELECT n.id, base.top + n.offset_from_top, n.date, n.category, n.title, n.summary,
       n.whats_new, n.how_to_use, n.setup, n.notes, n.tag
FROM new_rows n, base
ON CONFLICT (id) DO UPDATE SET
  position = EXCLUDED.position,
  date = EXCLUDED.date,
  category = EXCLUDED.category,
  title = EXCLUDED.title,
  summary = EXCLUDED.summary,
  whats_new = EXCLUDED.whats_new,
  how_to_use = EXCLUDED.how_to_use,
  setup = EXCLUDED.setup,
  notes = EXCLUDED.notes,
  tag = EXCLUDED.tag;

COMMIT;
