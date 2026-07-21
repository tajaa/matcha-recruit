-- /admin/updates changelog rows for everything merged 2026-07-20
-- (last update entry before this batch was the 2026-07-19 group, top row
-- 'matcha-work-tasks-split-and-test-fixes').
-- Idempotent: deletes each id first, shifts positions, inserts at top in
-- reverse-chronological order (newest = position 0).
-- Run against dev AND prod.

BEGIN;

DELETE FROM admin_updates WHERE id IN (
  'broker-company-chat',
  'pilot-grounding-uplift',
  'platform-cleanup-refactor'
);

UPDATE admin_updates SET position = position + 3;

INSERT INTO admin_updates (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) VALUES

(
  'broker-company-chat',
  0,
  '2026-07-20',
  'Broker',
  'Broker ↔ company chat — private threads about flagged data, claims and documents',
  'A broker and one of its linked client companies can now message each other inside the product instead of falling back to email. Threads can be anchored to the record being discussed (a claim, loss run, document, flagged data point, incident, submission or policy), so "about this claim" is a property of the thread rather than something everyone has to restate. Access rides the existing broker↔client relationship: no feature flag to turn on, and the moment a relationship ends the history disappears from both sides.',
  '["New Messages surface on the broker side (/broker/messages) and a Broker Chat entry on the company side (/app/broker-chat), both backed by the same threads.", "A thread — and any individual message — can carry a reference to the record under discussion: claim, loss run, document, flagged data, incident, submission, policy, or general.", "Per-user unread counts and badges on both sidebars, so two people at the same broker each track their own read state on a shared thread.", "Either side can archive a thread and either side can bring it back — status is shared, so this is not a broker-only control.", "Messages can be edited or deleted by their author; the conversation list preview rewrites to match.", "Retried sends collapse instead of duplicating, so a flaky connection does not post the same message twice."]',
  '["Broker: Messages in the left sidebar → New → pick a client company, optionally set a subject and attach a reference, then write the first message.", "Company: Broker Chat appears under Communication once a broker is actively linked to you. If no broker is linked, the page explains that rather than 404ing.", "Attach a reference with the paperclip in the composer, then give it a label (e.g. \"Claim #10432\") — a reference without a label is rejected.", "Tick \"Show archived\" above the conversation list to get back to an archived thread."]',
  NULL,
  '["No feature flag — the company side appears exactly when an active (or grace-period) broker link exists, and disappears when it does not.", "Ending a broker relationship hides the entire thread history from both parties immediately; it is not a soft hide the broker can read around.", "Platform admins cannot post here. The company side requires a real business-admin account, because an admin''s company context resolves to an arbitrary tenant and a message attributed to \"the client\" has to come from the client.", "Delivery is currently a short poll, not the live websocket the channels/inbox surfaces use — new messages land within a few seconds rather than instantly. Bell notifications are real-time."]',
  'new'
),

(
  'pilot-grounding-uplift',
  1,
  '2026-07-20',
  'AI Pilots',
  'Pilot grounding uplift — Broker, Legal, Handbook and Analysis Pilots can now cite records they could already see',
  'A pass across all four Pilots closing the same class of gap: data the platform already computed and already showed elsewhere (in a packet, a dashboard, a register) that the Pilot chat could not cite, so answers were vaguer than the evidence behind them. Each addition is a real record with a citation id, so anything the model asserts can be traced back to a row — and anything it cites that is not in the retrieved set is still stripped before the answer is shown.',
  '["Broker Pilot can now cite property analytics (catastrophe exposure, plans, per-peril tiers) and the client''s composite risk index with its component breakdown and uncertainty band — both were already in the submission packet but invisible to the chat.", "Broker Pilot can now cite fleet / driver-risk records: fleet grade, tier counts, overdue MVR reviews, and the individual drivers rated marginal or high-risk.", "Legal Pilot gains five new evidence sources — leave requests, agency charges (EEOC/NLRB/OSHA/state), pre-termination reviews, separation agreements, and post-termination claims — each with its custody trail.", "Handbook Pilot now drafts against the governing compliance requirement rather than the raw overlapping list, and grounds on the handbook''s own audit gaps and freshness findings; the tenant''s own handbook sections and policies are fed at full text instead of a 280-character preview.", "Analysis Pilot can now build datasets from the company''s own records — monthly incident counts and workers'' comp loss runs — instead of only from uploaded files."]',
  '["Nothing to switch on: each Pilot picks the new records up automatically on its next turn, for tenants that have the underlying product.", "Broker Pilot: ask about property exposure, the client''s risk index, or the fleet, and the answer will carry citations you can open.", "Analysis Pilot: on a new session, the dataset picker now offers the company''s own incident and loss-run series alongside file upload."]',
  NULL,
  '["Each new source is gated on the flag for the product that owns the data, so a tenant without that product contributes nothing — and the Pilot says the source is off rather than implying the records do not exist.", "Legal Pilot never selects free-text medical detail from leave records (reason, denial reason, notes) — only type, status, dates and the intermittent flag.", "Fleet grading is gated on the client''s own driver-risk flag rather than on the MVR table having rows, because the credentialing product writes to that same table and unscored rows would otherwise read as a spotless fleet.", "Directional figures (wind/wildfire tiers, employer-entered MVR data) carry that qualifier on the record itself, not just in the prompt, so the caveat survives into the citation."]',
  NULL
),

(
  'platform-cleanup-refactor',
  2,
  '2026-07-20',
  'Platform',
  'Codebase cleanup pass — structural splits, security fixes, and a dashboard 500 caught by the audit',
  'A large internal cleanup (404 files) executed against a 59-item plan, then independently audited item by item against the actual source rather than the plan''s own claims. Mostly invisible from the product, with two exceptions worth knowing about: two security hardening fixes, and a dashboard crash the audit found and fixed.',
  '["The biggest server files were split into packages: compliance_service, handbook_service, the admin / resources / compliance routers, the broker and provisioning routers, and matcha_work_document.", "Security: checkout redirects now go through an open-redirect guard, and the voice-interview websocket passes its token as a bearer subprotocol instead of in the URL query string.", "Fixed: GET /dashboard returned a 500 for some tenants after a model extraction dropped two imports — the failure only appeared at request time, so a clean boot did not catch it.", "Eleven oversized frontend components had their data-fetching logic extracted into dedicated hooks, and duplicated UI (pilot chrome, metric strips, public signing pages, register pages) was consolidated into shared primitives.", "Shared plumbing for repeated patterns: one SSE helper, one async-fetch hook, one websocket base class, one audit-log helper, one PDF-render path."]',
  '["Nothing to do — this is internal restructuring. If you saw an error on the Dashboard on 2026-07-20, it is fixed."]',
  NULL,
  '["The audit ran 56 independent verifiers, one per plan item, each reading the tree rather than the plan. 58 of 59 claims held; the one that did not was the dashboard bug above, which was fixed before the merge landed.", "Two items are honestly partial rather than done: the shared DataTable is adopted by 2 admin pages (not 5) and the shared Modal by 1 dialog, with ~64 files still on bespoke dialogs. Tracked in CLEANUP_AUDIT.md.", "Verification at merge: typecheck clean, 159 client tests green, server boots with all 1,858 routes registered."]',
  NULL
);

COMMIT;
