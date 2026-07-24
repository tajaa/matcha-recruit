-- /admin/updates changelog rows for everything merged 2026-07-21 through 2026-07-23
-- (last update entry before this batch was the 2026-07-20 group, top row
-- 'broker-company-chat').
-- Idempotent: deletes each id first, then inserts below the current minimum
-- position (lowest position = newest/top; this table drifts negative over
-- time — the 2026-07-20 batch's top row sits at -6, not 0 — so anchor off
-- MIN(position), never hardcode "position + N" or assume a 0-based sequence).
-- Run against dev AND prod.

BEGIN;

DELETE FROM admin_updates WHERE id IN (
  'schedule-intelligence-fair-workweek',
  'benefits-open-enrollment',
  'cappe-merlin-agentic-design',
  'admin-product-builder',
  'admin-ai-usage-ledger'
);

WITH base AS (
  SELECT COALESCE(MIN(position), 0) - 1 AS top FROM admin_updates
),
new_rows (id, offset_from_top, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) AS (
  VALUES

  (
    'schedule-intelligence-fair-workweek',
    0,
    '2026-07-23'::date,
    'Scheduling',
    'Schedule Intelligence — incident correlation, Fair Workweek exposure, and qualified-coverage analytics over your shift schedule',
    'Four read-time analytics modules layered on top of employee shift scheduling, none of which need an LLM call: whether understaffed shifts actually see more incidents, what predictive-scheduling ordinances would cost you in practice, whether attendance discipline lines up with a pattern of employer-caused schedule churn, and whether every upcoming shift has enough credentialed/trained coverage. HR Pilot''s hard-stop compliance gate for discipline now also reads the same codified ordinance table, so a scheduling change that would trigger Fair Workweek pay can be caught before it is saved, not just reported on afterward.',
    '["Incident-rate correlation between understaffed and adequately staffed shifts, split by location and day/night window, plus fatigue flags (short rest gap, long consecutive-day streak) for named employees on incident records — suppressed to counts-only under 10 incidents / 50 shifts so a small sample cannot look like a trend.", "Fair Workweek / predictive-scheduling dollar exposure priced against your own schedule-change history — currently covers NYC and Los Angeles ordinances with real citations; other Fair Workweek cities are intentionally left out until individually verified rather than guessed at.", "A discipline pretext shield: attendance write-ups are flagged (report-only, not blocking) when the employee''s own schedule shows elevated employer-initiated churn beforehand.", "Qualified-coverage view: for each upcoming published shift, how many assigned employees are actually credentialed/trained versus required.", "The discipline compliance gate and HR Pilot''s supervisor chat now both check the same Fair Workweek ordinance table before a scheduling change is saved, not just after."]',
    '["Turn on Employee Scheduling first, then Schedule Intelligence — the analytics page will tell you to enable scheduling if it is not on yet.", "Open Schedule Intelligence from the sidebar under Scheduling to see the four modules; each degrades gracefully (clearly labeled, not hidden) if the data behind it — credentials, training, or enough incident volume — is not yet present."]',
    NULL,
    '["Directional by design: the incident correlation is a pattern flag, not a causal claim, and the pretext shield is advisory only in this release — no discipline record is auto-blocked by it.", "Employee-initiated schedule changes (an approved swap/drop/unavailability request) are excluded from the Fair Workweek math before any dollar figure is calculated.", "Only NYC and LA carry a verified Fair Workweek citation right now; other US cities with similar ordinances are not yet in the table and will not appear as a false negative — they are simply absent until researched."]',
    'new'
  ),

  (
    'benefits-open-enrollment',
    -1,
    '2026-07-23'::date,
    'Benefits',
    'Open enrollment — plans, elections, and life events, now grounded into Matcha Work and HR chat',
    'A full open-enrollment workflow for employee benefits: admins publish plan options for a window, employees elect coverage (including dependents), and qualifying life events can reopen enrollment outside the normal window. The same election data now also grounds the AI assistants that already answer benefits questions, so a supervisor or employee asking about coverage gets an answer tied to what was actually elected, not just what the plan document says.',
    '["Admins configure benefit plans and an enrollment window, and employees elect coverage — including adding dependents — within that window.", "Qualifying life events (marriage, birth, loss of other coverage, etc.) can open a special enrollment period outside the normal cycle.", "Matcha Work threads and HR Pilot''s supervisor chat, plus employee Ask HR, can now cite actual enrollment/election records when answering benefits questions.", "Ask HR''s answers stay employee-safe — coworker-identifying detail is not exposed just because the underlying enrollment data now exists."]',
    '["Admin: set up plans and the enrollment window under Benefits, then notify employees enrollment is open.", "Employees elect coverage from their portal during the open window, or during a life-event window an admin opens for them.", "Ask a benefits question in Matcha Work, HR Pilot, or employee Ask HR and the answer will reference the tenant''s own plan/election data where relevant."]',
    NULL,
    '["Rides the existing benefits_admin feature — no new flag to turn on if benefits was already enabled.", "Grounding is read-only: the AI assistants cite enrollment data, they do not make or change elections on anyone''s behalf."]',
    'new'
  ),

  (
    'cappe-merlin-agentic-design',
    -2,
    '2026-07-23'::date,
    'Cappe',
    'Merlin gets a real design vocabulary, a Max tier, and — for paid tiers — the ability to see its own work before replying',
    'Merlin, the AI design chat in the Cappe site builder, moved from single-shot restyling to a much larger set of design controls plus, for paid tiers, an agentic loop that actually renders and screenshots the page it just edited before it answers — closing the gap where Merlin used to report success on changes that were invisible or broken on the live page.',
    '["Design vocabulary expanded: heading/body size scale, curated theme presets with font pairings, a motion/reveal-animation vocabulary with reduced-motion coverage, per-breakpoint responsive layout, section presets, a decorative lane (patterns, image filters, shape dividers), and bulk/duplicate-block operations that restyle several sections in one message.", "New Max tier on top of Lite (free, single-shot) and Regular (paid): higher reasoning effort for complex or multi-part requests, at a longer timeout.", "Regular and Max now run an agentic tool loop — apply the requested changes to a working copy, render it, look at a screenshot of the result, and revise before replying — instead of answering blind. Lite stays single-shot for speed.", "Conversations persist server-side as multiple named threads per page (replacing local-browser-only history), with automatic tier routing per message and support for attaching images (as a placement reference, a style reference, or generation input).", "AI-generated images now default to 2K resolution (was 1K), are cataloged in a per-site asset library for reuse, and can be dragged onto sections or retargeted onto a different section via an \"Apply to…\" menu; live spend (model, size, estimated cost) shows during generation.", "New slash commands (/add-section, /generate-image, /restyle, /theme, /light-mode, /dark-mode) and fixed light/dark mode switching, which previously reported success without changing anything."]',
    '["Nothing to switch on — open Merlin in the Cappe editor as before; the expanded vocabulary, tiers, and agentic loop apply automatically based on request complexity.", "Use the asset library to reuse a previously generated image instead of regenerating it, and the new \"Apply to…\" menu to move an existing image onto a different section."]',
    NULL,
    '["Both Gemini model tiers moved onto GA models this window (off preview versions), and the image-generation model was migrated off a preview model Google shut down on 2026-06-25 — image generation would otherwise have been broken.", "The Max tier briefly shipped with a real bug (a 2.5-era thinking parameter the newer models reject), which broke Merlin''s default tier for part of a day before being fixed the same day.", "2K-default and the asset library apply going forward only — images generated before this change are not re-generated at higher resolution."]',
    'new'
  ),

  (
    'admin-product-builder',
    -3,
    '2026-07-21'::date,
    'Platform',
    'Admin product builder — compose a sellable package from feature flags without a code deploy',
    'New admin tool at /admin/products for assembling a custom, sellable product out of existing feature flags, pricing it, and publishing a live signup link — the piece that had been designed into the codebase''s "custom products" model but not yet built as an actual admin UI.',
    '["Pick a whitelisted set of feature flags, a paid gate feature, a pricing mode (per-seat / block / flat via Stripe, free-at-signup, or contact-sales), and a nav order, then publish to get a live /p/<slug>/signup link with no code deploy.", "Signups are tagged with a namespaced signup_source (product:<slug>) so a custom product can never collide with a hardcoded one.", "Grants are locked in at signup/payment time rather than computed live, so editing a published product does not silently change what existing customers on it already have.", "A separate re-sync action re-applies an edited product''s features to its already-activated tenants on demand."]',
    '["Admin: Products in the admin nav → choose features, set pricing and gate, publish.", "Share the generated /p/<slug>/signup link directly with a prospect once published."]',
    NULL,
    '["Editing a live product does not retroactively regrant existing tenants — run the sync-tenants action if you want already-activated customers to pick up an edit.", "Feature selection is whitelisted, not free-form — only flags cleared for self-serve signup/billing can be added to a product."]',
    'new'
  ),

  (
    'admin-ai-usage-ledger',
    -4,
    '2026-07-21'::date,
    'Platform',
    'AI usage ledger — a real cost/latency log for every Gemini call in the platform',
    'New admin dashboard at /admin/ai-usage tracking every Gemini call across the whole codebase — cost, latency, errors — broken down by feature and by model, backed by a new logging layer that required no changes at any of the ~100 existing call sites. A same-window bug that silently dropped every image-generation row from the ledger was found and fixed before it went unnoticed for long.',
    '["Dashboard shows stat cards, cost-by-hour, and rollups by feature and by model, with a filterable/drillable call log including full error text for failed calls.", "Logging is automatic for every Gemini call (sync, async, and streaming) via the shared client factory — no per-feature instrumentation needed going forward.", "Cost attribution for Cappe''s Merlin was split out by cost center (the agent loop itself vs. its image-generation tool vs. the plain image-gen button), so spend on each is visible separately instead of lumped together.", "A pricing gap for one image-generation model that was logging cost as unpriced/null was fixed, and a separate bug where image-generation calls specifically were being silently dropped from the ledger entirely (a background-thread/event-loop mismatch) was found and fixed."]',
    '["Admin: AI Usage in the admin nav, alongside Server Errors and Traffic."]',
    NULL,
    '["Distinct from the existing per-user rate limiter — that guards call counts; this is the actual cost/latency record.", "The image-generation drop bug means any AI-usage numbers reviewed before this fix understated true spend — historical rows for that gap cannot be recovered, only prevented going forward."]',
    NULL
  )
)
INSERT INTO admin_updates (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag)
SELECT n.id, base.top + n.offset_from_top, n.date, n.category, n.title, n.summary,
       n.whats_new, n.how_to_use, n.setup, n.notes, n.tag
FROM new_rows n, base;

COMMIT;
