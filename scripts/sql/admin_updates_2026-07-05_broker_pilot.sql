-- /admin/updates changelog row for the 2026-07-05 Broker Pilot launch.
-- Idempotent: deletes the id first, shifts positions, inserts at 0.
-- Run against dev AND prod (psql via app-EC2 tunnel) so both environments
-- show the same changelog.

BEGIN;

DELETE FROM admin_updates WHERE id = 'broker-pilot-grounded-client-analysis-chat';

UPDATE admin_updates SET position = position + 1;

INSERT INTO admin_updates (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) VALUES
(
  'broker-pilot-grounded-client-analysis-chat',
  0,
  '2026-07-05',
  'Broker',
  'Broker Pilot — grounded per-client analysis chat over uploaded carrier documents + platform data (Broker Pro)',
  'Broker Pro brokers get an open-ended analysis workbench per client: upload the carrier documents they already hold — loss runs, dec pages, competing quotes, carrier letters — and interrogate them together with the platform data on file (WC metrics, EPL readiness, limits, loss development, property). Every answer cites its underlying records; an anti-hallucination gate drops any claim citing a record that does not exist. Exports a broker-branded analysis-memo PDF.',
  '["New /broker/pilot workbench (Pro sidebar entry): sessions grouped by client, chat console with numbered evidence cards + citation chips, documents panel, and a grounding-scope panel showing exactly what the AI can see.", "Per-client sessions for both on-platform companies and off-platform (External Book) clients — same scoring data the submission packet uses grounds the chat.", "Document uploads (PDF/DOCX/TXT/CSV, 15 MB, 12 per session) are classified + key-figure-extracted by Gemini once at upload and persist to private S3; a failed extraction degrades to text-only grounding, never a dead upload.", "Grounded chat turns cite corpus IDs only — platform sections (WC, EPL factors, coverage lines, loss periods, property) and uploaded docs/figures; invented citations are stripped before display and surfaced as a note.", "Analysis-memo PDF: narrative, grounded observations with footnote citations, open questions, evidence index, and a deterministic appendix rendered from the stored extractions and platform data — never from model text.", "Entry points: Pilot tab on every client detail page and a Broker Pilot button on external-client pages, deep-linking into a prefilled session."]',
  '["Open Broker Pilot in the broker sidebar (Pro) → New session → pick a platform or external client.", "Upload the client''s loss runs / dec pages / quotes, wait for the Analyzed badge, then ask: \"Compare the quoted premium against the loss history — is the pricing supported?\"", "Export memo once the analysis has at least one answer — the PDF downloads immediately and stays available under the session."]',
  '["Run migration brokerpilot01 (5 tables: sessions, messages, documents, packets, audit log) via migrate-dev.sh + migrate-prod.sh before enabling.", "Broker needs plan=''pro'' (brokers table, admin-toggled) — every endpoint is Pro-gated.", "Private S3 bucket must be configured (document + memo storage); uploads 503 without it.", "Rate limits: 20 document uploads and 30 chat turns per broker per hour."]',
  '["Documents are analyzed once at upload; chat turns never re-send file bytes — the corpus carries extractions plus capped raw text for the 5 most recent docs.", "The AI is an analyst, not an advisor: it will not recommend buying or declining coverage, and flags that quotes/forms must be verified against actual policy language.", "Every session mutation, chat turn, upload, memo generation, and download lands in broker_pilot_audit_log."]',
  'action-needed'
);

COMMIT;
