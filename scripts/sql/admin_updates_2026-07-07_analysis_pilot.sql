-- /admin/updates changelog row for the 2026-07-07 Analysis Pilot launch
-- (bring-your-own-data engine, general-purpose rename from Risk Pilot, and
-- the follow-on analyst/context/caching upgrades from the same arc).
-- Idempotent: deletes the id first, shifts positions, inserts at 0.
-- Run against dev (applied) AND prod (psql via app-EC2 tunnel) so both
-- environments show the same changelog.

BEGIN;

DELETE FROM admin_updates WHERE id = 'analysis-pilot-general-data-engine-plus-analyst-upgrades';

UPDATE admin_updates SET position = position + 1;

INSERT INTO admin_updates (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) VALUES
(
  'analysis-pilot-general-data-engine-plus-analyst-upgrades',
  0,
  '2026-07-07',
  'Analysis Pilot',
  'Analysis Pilot — general-purpose bring-your-own-data analysis chat (renamed from Risk Pilot), plus analyst-grade reasoning, memory, and speed upgrades',
  'Upload your own CSV/XLSX/financial-document data and get a grounded chat analyst over it — every number it cites is computed deterministically, never guessed. Renamed from Risk Pilot to Analysis Pilot as the engine grew from a risk-only tool into a general data-analysis assistant, and picked up sharper analytics, hierarchical reasoning, long-session memory, and a context cache that makes repeat turns faster and cheaper.',
  '["Upload a CSV, XLSX, or financial-document PDF (10-Ks, P&Ls, loss runs, inventory) — a deterministic engine computes metrics through pluggable analyzer packs (general stats, volatility & risk, financial ratios, insurance loss, inventory ops) over one normalized model, so the chat has real numbers to cite before you ask anything.", "Renamed Risk Pilot → Analysis Pilot: volatility/risk is now one analyzer pack among several rather than the product''s identity, reflecting the general-purpose data-analysis chat it''s become. New general-analysis mode plus highlight-to-chat — click any computed record in the Metrics tab to focus your next question on it.", "Domain-aware analyst framing: the assistant automatically reasons like a quant, a corporate-finance analyst, a P&C underwriter, or an ops/inventory analyst depending on which packs actually fired on your data — a mixed upload gets all the relevant lenses, a plain CSV gets none.", "Sharper deterministic signals: trend-reliability scoring (is a trend real or just noise?), outlier flagging, seasonality detection across real multi-year cycles, return-distribution shape (fat vs. thin tails), rolling-volatility regime shifts, and drawdown timing (peak → trough → recovery) — every one a cited, computed number.", "The assistant now decomposes your question into sub-questions and works each one against the data before answering, and surfaces data-quality caveats (unverified figures, truncated series) instead of silently dropping them.", "Long sessions no longer forget: older turns auto-compact into a running summary that preserves every cited number, with a session cap and a friendly nudge to generate a report and start fresh once you''re deep into a thread.", "Repeat turns in the same session are faster and cheaper — the (often large) dataset-and-analysis context is cached once and reused instead of being resent on every message."]',
  '["Open Analysis Pilot from the sidebar, start a session, and drop in a CSV/XLSX file or a financial PDF.", "Review any document-extracted figures before analysis runs (never auto-trusted); then ask anything — \"summarize this,\" \"what''s the trend,\" \"which series is riskiest\" — every cited number traces back to something actually computed from your data.", "Click a record in the Metrics tab to focus the conversation on it.", "Generate an analyst report PDF once you''ve talked through the data — long sessions eventually hit a conversation cap, so wrap a long thread into a report and start a new session for the next dataset."]',
  '["Default off — enable per company via /admin/features → \"Analysis Pilot\" (same admin-toggle pattern as Legal Pilot; not bundled into any tier)."]',
  '["Same grounding discipline as the rest of the Pilot family: cited numbers are always traced to a deterministic computation, never a model guess — and the internal flag/table names (analysis_pilot) reflect the rename, no data migration needed."]',
  'action-needed'
);

COMMIT;
