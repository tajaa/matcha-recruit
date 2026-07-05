-- /admin/updates changelog rows for the 2026-07-05 Legal Pilot batch.
-- Idempotent: deletes the two ids first, shifts positions, inserts at 0/1.
-- Run against dev (applied) AND prod (psql via app-EC2 tunnel) so both
-- environments show the same changelog.

BEGIN;

DELETE FROM admin_updates WHERE id IN (
  'legal-pilot-matter-scoping-intake-seed-caselaw',
  'legal-pilot-phase1-intake-parse-chronology-deadlines'
);

UPDATE admin_updates SET position = position + 2;

INSERT INTO admin_updates (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) VALUES
(
  'legal-pilot-phase1-intake-parse-chronology-deadlines',
  0,
  '2026-07-05',
  'Legal Pilot',
  'Legal Pilot — complaint-PDF intake, chronology, response deadlines, counsel-opened alerts, matter-aware starters',
  'Phase 1 of the Legal Pilot roadmap: upload the served document to prefill intake, a merged record chronology (tab + PDF section), hard response-deadline tracking with 14/7/3/1-day reminders, an email when counsel first opens a shared packet, and starter prompts shaped by matter type.',
  '["Upload the served complaint / subpoena / EEOC charge PDF on the New Matter form — Gemini extracts type, caption, allegation, dates, state, and response deadline as an editable draft (parse-and-discard; never auto-creates the matter).", "New Chronology tab beside the Analyst console: every dated company record in scope, month-grouped oldest-first, click-through to the full record; the memo PDF gains a deterministic Chronology of records section.", "Matters carry a response deadline (+ note): masthead countdown chip (amber ≤7d, red ≤3d/overdue) and a legal_deadline_reminders worker that emails the owner at 14/7/3/1 days out, deduped per bucket+deadline via the audit log.", "The matter owner is emailed the first time a shared packet link is downloaded — closes the loop on Send to counsel (chain-of-custody already logged every download).", "Console starter prompts now match the matter type (EEOC, subpoena, audit, class action, single-plaintiff) instead of a static wage-hour set.", "ER cases now honor the matter location/state scope via their involved-employees links; cases naming no employees deliberately stay in scope."]',
  '["New matter → \"Upload the served document (PDF) to prefill\" → review every extracted field before Create.", "Open a matter → Chronology tab for the timeline; regenerate the memo PDF to get the chronology section.", "Set \"Response deadline\" on intake to get the countdown chip + reminder emails."]',
  '["Run migration legaldef03 (adds legal_matters.response_deadline / deadline_note) via migrate-dev.sh + migrate-prod.sh — matter creation references the new columns.", "Enable the reminder worker: INSERT a scheduler_settings row task_key=''legal_deadline_reminders'' enabled=true (default off, repo convention).", "Intake parse is rate-limited 10/company/hour; 15 MB PDF cap."]',
  '["Intake extraction is a draft — the matter is only created after human review (same rule as IR voice intake).", "Chronology excludes compliance-requirement posture rows on purpose: their change date is the law''s, not a company action."]',
  'action-needed'
),
(
  'legal-pilot-matter-scoping-intake-seed-caselaw',
  1,
  '2026-07-05',
  'Legal Pilot',
  'Legal Pilot — evidence scoped to the matter, intake-seeded first analysis, case-law search fixed + discoverable',
  'Evidence sidebar/chat/packet now filter to the matter''s location or state instead of the whole company; the console auto-runs a first analysis from the intake form instead of asking you to re-describe the claim; case-law research actually returns cases and is reachable from an empty matter.',
  '["Matter-scoped evidence: every location-capable source (IR/OSHA, compliance, alerts, discipline, training, accommodations) filters by the matter''s location — exact match first, employee work-state fallback — with an \"Evidence scoped to …\" note in the panel and packet. Policies stay company-wide by design.", "Just-created matters auto-send a first analyst turn recapping the intake allegation/context/timeframe — no more retyping what the form already captured.", "Case-law search rebuilt: keyword ladder (matter type + allegation keywords, broadening until results) replaces the full-sentence query that CourtListener matched to zero; complete-but-empty runs now say what was searched instead of rendering a blank panel.", "Legal landscape panel: matters created without a location/state get an inline jurisdiction setter (previously a dead end — the Research button could never appear), plus a hint explaining Research finds court decisions + public guidance (~2 min).", "Masthead shows scope + honest tooltips on the law/case-law chips."]',
  '["Set a location (or 2-letter state) on the matter — via intake or the Legal landscape panel — to scope evidence and unlock Research.", "Create a matter with the allegation filled in: the first analysis runs itself.", "Research → \"Case law only\" for a fast refresh; full Research adds the public-guidance summary."]',
  NULL,
  '["Location scoping prefers the employee''s work-location link and falls back to work state — employees with neither are excluded while a scope is active (matches compliance-service convention).", "Matters with no location/state keep today''s company-wide behavior."]',
  NULL
);

COMMIT;
