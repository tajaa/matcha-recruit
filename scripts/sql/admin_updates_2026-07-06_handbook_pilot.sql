-- /admin/updates changelog row for the 2026-07-06 Handbook Pilot launch.
-- Idempotent: deletes the id first, shifts positions, inserts at 0.
-- Run against dev (applied) AND prod (psql via app-EC2 tunnel) so both
-- environments show the same changelog.

BEGIN;

DELETE FROM admin_updates WHERE id = 'handbook-pilot-grounded-handbook-policy-drafting';

UPDATE admin_updates SET position = position + 1;

INSERT INTO admin_updates (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) VALUES
(
  'handbook-pilot-grounded-handbook-policy-drafting',
  0,
  '2026-07-06',
  'Handbook Pilot',
  'Handbook Pilot — grounded conversational handbook & policy drafting (Pro + Matcha-X)',
  'A business admin opens a session and converses with a grounded AI that drafts handbook sections and standalone policies from the company''s own material — jurisdiction requirements for its actual work locations, its industry baseline, and its existing handbook/policies — with every enforceable clause traced to a real requirement id and nothing published without human review.',
  '["New Handbook Pilot session: chat drafts handbook sections and policies grounded in the company''s applicable jurisdiction requirements (same corpus the template generator and handbook audit read) plus the industry playbook baseline and existing sections/policies — not generic boilerplate.", "Enforceable clauses must cite a bracketed jurisdiction/corpus id; the same anti-hallucination gate used by Legal Pilot drops any uncited reference before a draft ever reaches the admin.", "Drafts are reviewable and editable, never auto-published: the admin edits proposed sections/policies, then explicitly Promotes each one into a real draft handbook or policy — nothing goes live without that step.", "Full session transcript + every edit/promotion is audit-logged."]',
  '["Open Handbook Pilot from the sidebar, start a session describing what you need (e.g. \"draft a remote-work policy\" or \"build out the leave section\").", "Review each drafted section/policy in the panel — check the cited jurisdiction ids, edit the language as needed.", "Click Promote on anything you want live — sections land in a new draft handbook, policies via the normal policy flow — then finish publishing through the existing Handbooks/Policies pages as usual."]',
  '["Default off — enable per company via /admin/features → \"Handbook Pilot\". New Pro/bespoke and Matcha-X signups get it automatically (Matcha-X via the tier overlay, Pro stored true at signup, matching Handbook Audit) — existing companies from before this shipped need the toggle backfilled by hand."]',
  '["Same grounding discipline as Legal Pilot: the AI never invents a jurisdiction requirement — anything it can''t cite gets dropped before you see it.", "Promote never overwrites a live handbook in place — it always creates a new draft you review through the normal handbook workflow."]',
  'action-needed'
);

COMMIT;
