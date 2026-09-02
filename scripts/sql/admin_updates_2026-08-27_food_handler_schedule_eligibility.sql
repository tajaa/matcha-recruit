-- /admin/updates entry for food-handler-card scheduling safeguards.
-- Idempotent and safe to run against dev and prod. This is content only;
-- migrations and scheduler enablement remain separate deployment actions.

BEGIN;

DELETE FROM admin_updates
WHERE id = 'pr-306-food-handler-card-scheduling-safeguards';

WITH base AS (
  SELECT COALESCE(MIN(position), 0) - 1 AS top
  FROM admin_updates
)
INSERT INTO admin_updates
  (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag)
SELECT
  'pr-306-food-handler-card-scheduling-safeguards',
  base.top,
  '2026-08-27'::date,
  'Employee Scheduling',
  'Food Handler Cards — advance reminders and automatic schedule protection',
  'Food Handler Cards now have an end-to-end scheduling safety net: confirmed document expiry dates, two-week reminders, automatic removal from future affected shifts at expiry, and enforcement across manual scheduling, Huume changes, swaps, and publishing.',
  '["Food Handler Card evidence now keeps the manager-confirmed expiration date; AI extraction is advisory and cannot authorize scheduling by itself.", "Fourteen days before expiry, Matcha notifies the employee once and the responsible location managers for each affected location.", "When the card expires, future affected shifts are removed automatically and the employee cannot be added, moved, swapped, or published onto affected work until a renewed card is approved.", "The same credential check now runs for Huume-assisted schedule edits and before a draft is published, closing routes that previously could bypass assignment-time checks.", "Every warning delivery and schedule-enforcement decision is recorded so managers can audit what happened."]'::jsonb,
  '["Employees -> Schedule -> Full shift editor -> Jobs & credentials: add Food Handler Card as a required credential on each affected job.", "Employees -> open the employee -> Credentials: upload the Food Handler Card and approve the document with its confirmed expiration date.", "Use the roster markers and the schedule eligibility cases to address expiring or expired cards before building coverage. A replacement document clears the block after approval.", "Use Ask Huume to check eligibility or explain an open case, then review any proposed schedule change before confirming it."]'::jsonb,
  '["Apply migrations empsched11 through empsched15, including the notification-delivery table, before enabling this capability.", "Enable the employee_schedule and credential_templates company features, then enable the schedule_eligibility scheduled task so reminders and automatic removals run."]'::jsonb,
  '["Food Handler Card protection is limited to jobs where the credential is explicitly required; unrelated jobs remain unaffected.", "A manager can choose qualified roster members, but cannot override a missing, unconfirmed, or expired required Food Handler Card.", "Other expiring credential policies continue to use their configured manager-review flow unless that credential type is explicitly set to auto-remove future shifts."]'::jsonb,
  'action-needed'
FROM base;

COMMIT;
