-- Backfill /admin/updates for the customer-relevant releases merged from
-- 2026-08-25 through 2026-08-27. Replaces the earlier single-row food-handler
-- insert so all five rows are ordered as one idempotent, chronological batch.

BEGIN;

DELETE FROM admin_updates
WHERE id IN (
  'pr-306-food-handler-card-scheduling-safeguards',
  'aug25-27-huume-conversation-reliability',
  'pr-290-matcha-work-kanban-autopr',
  'aug25-schedule-job-credentials-and-breaks',
  'pr-266-inventory-sales-mapping-recipe-parity'
);

WITH base AS (
  SELECT COALESCE(MIN(position), 0) - 5 AS top
  FROM admin_updates
),
new_rows (id, offset_from_top, date, category, title, summary, whats_new, how_to_use, setup, notes, tag) AS (
  VALUES
  (
    'pr-306-food-handler-card-scheduling-safeguards',
    0,
    '2026-08-27'::date,
    'Employee Scheduling',
    'Food Handler Cards — advance reminders and automatic schedule protection',
    'Food Handler Cards now have an end-to-end scheduling safety net: confirmed document expiry dates, two-week reminders, automatic removal from future affected shifts at expiry, and enforcement across manual scheduling, Huume changes, swaps, and publishing.',
    '["Food Handler Card evidence now keeps the manager-confirmed expiration date; AI extraction is advisory and cannot authorize scheduling by itself.", "Fourteen days before expiry, Matcha notifies the employee once and the responsible location managers for each affected location.", "When the card expires, future affected shifts are removed automatically and the employee cannot be added, moved, swapped, or published onto affected work until a renewed card is approved.", "The same credential check now runs for Huume-assisted schedule edits and before a draft is published, closing routes that previously could bypass assignment-time checks.", "Every warning delivery and schedule-enforcement decision is recorded so managers can audit what happened."]'::jsonb,
    '["Employees -> Schedule -> Full shift editor -> Jobs & credentials: add Food Handler Card as a required credential on each affected job.", "Employees -> open the employee -> Credentials: upload the Food Handler Card and approve the document with its confirmed expiration date.", "Use the roster markers and the schedule eligibility cases to address expiring or expired cards before building coverage. A replacement document clears the block after approval.", "Use Ask Huume to check eligibility or explain an open case, then review any proposed schedule change before confirming it."]'::jsonb,
    '["Apply migrations empsched11 through empsched15, including the notification-delivery table, before enabling this capability.", "Enable the employee_schedule and credential_templates company features, then enable the schedule_eligibility scheduled task so reminders and automatic removals run."]'::jsonb,
    '["Food Handler Card protection is limited to jobs where the credential is explicitly required; unrelated jobs remain unaffected.", "A manager can choose qualified roster members, but cannot override a missing, unconfirmed, or expired required Food Handler Card.", "Other expiring credential policies continue to use their configured manager-review flow unless that credential type is explicitly set to auto-remove future shifts."]'::jsonb,
    'action-needed'
  ),
  (
    'aug25-27-huume-conversation-reliability',
    1,
    '2026-08-26'::date,
    'Huume',
    'Huume conversations — reliable follow-through, flexible drafts, and grouped schedule edits',
    'Huume now keeps multi-turn context reliably, makes progress with partial information, delivers offer notifications more consistently, and can stage related schedule changes together for one review.',
    '["Huume planner and tool follow-ups use the OpenAI Luna route while keeping the existing confirmation and tool-use guardrails.", "Later turns now preserve assistant history correctly, so follow-up questions and schedule conversations continue instead of failing after the first reply.", "Offer drafting can progress from partial information and asks a concise human follow-up for genuinely missing decisions instead of exposing internal schema fields.", "Signed-offer events are persisted before slow PDF or email work, so chat and in-app delivery are not lost to background failures.", "Huume can group up to four related schedule edits into one confirmed proposal and explains readiness or feature-gate blockers early."]'::jsonb,
    '["Ask Huume in the relevant Matcha Work thread or Schedule Editor, then answer its short follow-up questions in the same conversation.", "For a schedule change, describe all related edits together; review the combined proposal and confirm only when every change is correct.", "For offers, provide what you know first, then fill in the specific detail Huume asks for rather than starting a new draft."]'::jsonb,
    NULL,
    '["Huume still requires an explicit confirmation before it writes a schedule change.", "The assistant acts on safe, reversible work first; high-impact actions remain staged for human review."]'::jsonb,
    'new'
  ),
  (
    'pr-290-matcha-work-kanban-autopr',
    2,
    '2026-08-26'::date,
    'Matcha Work',
    'Kanban AutoPR — turn a scoped task into a reviewable pull request',
    'Adds an operations-controlled automation that takes an eligible Matcha Work Kanban card through implementation into a draft pull request, then keeps the card linked to that PR and its review state.',
    '["Eligible Kanban cards can move from todo to in progress, review, and merged state as the associated pull request advances.", "Cards display a validated pull-request link and number so implementation and review stay connected in the workspace.", "The automation is constrained to configured service projects and opens a draft PR for human review rather than merging work automatically.", "PR identity and link validation protect the board from forged cross-project updates or unsafe links."]'::jsonb,
    '["Use a configured service project and place a well-scoped card in todo or changes requested.", "Review the generated draft PR and its linked Kanban card; merge through the normal code-review process.", "Use the card state and PR link as the shared source of truth for implementation progress."]'::jsonb,
    '["Apply migration taskpr0001 and configure the authorized bot account, runner environment, GitHub webhook, and project allowlist before enabling the scheduled workflow.", "Run the production seed pack and a manual workflow dry run before relying on the scheduler."]'::jsonb,
    '["This is an operations automation, not a general end-user code-generation control.", "It creates draft PRs only; merge authority remains with the normal reviewer workflow."]'::jsonb,
    'action-needed'
  ),
  (
    'aug25-schedule-job-credentials-and-breaks',
    3,
    '2026-08-25'::date,
    'Employee Scheduling',
    'Qualified scheduling — job credentials, minor permits, and planned breaks',
    'Scheduling gained job-specific qualification and credential controls, grace periods for new hires, minor work-permit checks, and planned-break guidance so managers can build a compliant schedule before publishing it.',
    '["Configure required credentials and a grace period per scheduling job; a credential rule protects only the work where it is required.", "Missing, unverified, expiry-unconfirmed, or expired required credentials block scheduling across create, assign, duplicate, and other direct assignment paths.", "Employee profiles now retain minor-status and work-permit information, and missing or expired permits block a minor from being scheduled at the affected location.", "Shift and template forms support planned break minutes, and meal-break conflicts open the affected shift for repair instead of falling through to a generic force action.", "Credential expiry cases and schedule guidance are location-aware, idempotent, and visible to managers for review."]'::jsonb,
    '["Employees -> Schedule -> Full shift editor -> Jobs & credentials: add the jobs your location schedules, choose qualified employees, select required credentials, and set any job-specific grace period.", "Employees -> open an employee -> Credentials or Minor compliance: upload and review the required document or permit before assigning restricted work.", "When creating a shift or template, enter planned break minutes. Resolve any break guidance in the shift inspector before publishing.", "Use roster markers and schedule eligibility cases to see why an employee cannot be placed on a particular job."]'::jsonb,
    '["Apply migrations empsched09 through empsched13 and invitefix01 before enabling the associated controls.", "Enable employee_schedule and credential_templates for the company, and provide a location timezone before publishing a schedule."]'::jsonb,
    '["A manager may deliberately override an ordinary roster qualification, but not a missing or expired schedule-blocking credential or work permit.", "Existing employees remain schedulable according to their existing records until a job rule or required credential applies to their work."]'::jsonb,
    'action-needed'
  ),
  (
    'pr-266-inventory-sales-mapping-recipe-parity',
    4,
    '2026-08-25'::date,
    'Inventory',
    'Sales imports and recipes — reliable mapping review with component-level control',
    'Inventory sales imports now decode recipe mappings correctly and give managers the same direct, recipe, or ignore controls in the import review that they have in the standalone mappings area.',
    '["Sales exports with recipe-mapped items render correctly instead of failing when mapping components are returned from the database.", "Import review explicitly lets a manager choose direct inventory, recipe, or ignore for every sold line.", "Recipe mappings support a per-component unit so the stock deduction reflects the actual recipe structure.", "Import failures show the underlying backend message instead of a generic parse-error toast."]'::jsonb,
    '["Work -> Inventory -> Sales import: upload the export and review every unmapped or recipe-mapped line.", "Choose Direct, Recipe, or Ignore explicitly; for a recipe, confirm each component and its unit before committing.", "Use the detailed import error if a source file needs correction, then re-upload after fixing it."]'::jsonb,
    NULL,
    '["Recipe mappings deduct each configured component when the sale is committed.", "Ignored lines remain out of inventory demand and stock movement calculations until they are mapped."]'::jsonb,
    'new'
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
