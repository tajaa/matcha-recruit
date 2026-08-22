# Schedule Huume implementation plan

## Objective

Replace the schedule editor's narrow command parser with a real, durable Huume conversation that is scoped to one manager, location, and editor week. The agent must inspect the real schedule, reason about coverage and compliance, stage changes, and require a later explicit confirmation before writes.

## Architecture

### Durable session

- A schedule assistant session maps exactly one `(company_id, user_id, location_id, week_start)` to one `mw_threads` record.
- The thread uses `huume_mode=true` and `surface='schedule_assistant'`.
- The session API returns the thread id, persisted messages, state, and version; reopening the same location/week resumes the same conversation.
- Schedule threads are excluded from the normal Matcha Work thread list.

### Huume surface scope

`HuumeSurfaceContext` carries the server-authoritative scope for every turn:

- `location_id`
- `week_start` and inclusive `week_end`
- allowed tool names and lookup topics
- draft-only write mode

The dispatcher resolves this scope from the session mapping on every message, rather than trusting client-supplied location or week data.

### Authorization

- Admin/client users may manage all active company locations.
- Employee users need an active manager or supervisor employee record at the selected location.
- The session owner must match the caller for every turn.
- Generic Matcha Work remains unavailable to ordinary employees; the narrowly scoped schedule surface is the exception.
- Every schedule write rechecks its location and employee/assignment relationship in the domain writer.

## Backend implementation map

| Area | Files | Main interfaces |
| --- | --- | --- |
| Schema | `server/alembic/versions/huumesched01_schedule_assistant_sessions.py` | `mw_threads.surface`; `schedule_assistant_sessions`; `schedule_digest_deliveries` |
| Session API | `server/app/matcha/routes/employee_schedule/assistant.py` | `POST /employee-schedule/assistant/sessions` |
| Session service | `server/app/matcha/services/scheduling/schedule_assistant_session.py` | `get_or_create_schedule_assistant_session`, `resolve_schedule_assistant_scope` |
| Huume scope | `server/app/matcha/services/huume/scope.py` | `HuumeSurfaceContext`, `SCHEDULE_TOOLS`, `SCHEDULE_LOOKUP_TOPICS` |
| Turn dispatch | `server/app/matcha/services/matcha_work/turn_pipeline.py` | `_run_huume_dispatch` passes surface context to `run_huume_turn` |
| Prompt and tools | `server/app/matcha/services/huume/prompt.py`, `server/app/matcha/services/huume/tools.py` | schedule-only prompt and filtered Gemini declarations |
| Agent execution | `server/app/matcha/services/huume/agent.py` | tool allow-list, deterministic reads, staged actions, confirmation execution |
| Domain writes | `server/app/matcha/services/scheduling/schedule_assistant_actions.py` | note, waiver, permit, and eligibility-case writers |
| Digest worker | `server/app/matcha/services/scheduling/daily_digest.py`, `server/app/workers/tasks/schedule_daily_digest.py` | idempotent manager/employee daily email delivery |

## Schedule tools

The schedule surface exposes only these tools:

1. `get_schedule_overview`
2. `list_schedule_eligibility_cases`
3. `find_shift_coverage`
4. `propose_schedule_change`
5. `propose_assignment_note`
6. `propose_meal_break_waiver`
7. `propose_work_permit`
8. `propose_eligibility_case_decision`
9. `lookup_context` for roster, employee, schedule, credentials, training status, and locations
10. `finish`

No onboarding, offers, discipline, inventory, or other general Matcha Work tools are declared to this agent.

## Confirmation protocol

Every mutating tool follows the same two-turn protocol:

1. First tool call creates `current_state.huume_action` with `status='proposed'` and a generated `confirm_id`.
2. Huume explains the proposed operation and asks for confirmation.
3. On a later turn, Huume must pass the exact stored `confirm_id`.
4. `evaluate_huume_action` checks feature entitlement, surface authorization, required fields, IDs/dates, and acknowledgement requirements.
5. The shared writer performs its own transactional location/assignment checks and creates an audit entry.
6. State becomes `applied` or `failed`; the UI reloads the schedule on success.

### Actions

- **Schedule change:** Uses the existing schedule proposal builder, always scoped to the session location/week and staged before application.
- **Assignment note:** One editable note per employee-shift with employee visibility, location-digest visibility, and employee-notice flags.
- **Meal waiver:** Records a manager attestation that the signed waiver is on file (or is not), then refreshes future break guidance.
- **Work permit:** Records a location-specific, manager-confirmed work permit and supersedes the previous active permit.
- **Eligibility decision:** `remove` deletes pending affected assignments; `keep` requires an explicit acknowledgement plus a written compliance-risk note of at least 20 characters.

## Daily digest

`send_location_daily_digest`:

- Sends the location manager/operations digest with break guidance and notes marked for location visibility.
- Sends an employee their own visible note/break guidance only when employee notice is enabled.
- Uses `schedule_digest_deliveries` to prevent duplicate sends per location, recipient, type, and date.
- Removes the idempotency claim if email delivery fails, allowing a retry.
- Is scheduler-gated by `scheduler_settings.schedule_daily_digest`, seeded disabled for safe rollout.

## Frontend implementation

| File | Responsibility |
| --- | --- |
| `client/src/components/employees/schedule-editor/ScheduleHuumePanel.tsx` | Hydrates durable session, renders real Huume history/timeline, streams canonical Matcha Work responses, refreshes schedule after writes |
| `client/src/api/employees/scheduleChat.ts` | `getScheduleHuumeSession(locationId, weekStart)` API client |
| `client/src/ops/pages/ScheduleEditor.tsx` | Mounts the Huume panel in place of the legacy parser panel |

The panel must not parse commands, fabricate an assistant response, or apply a schedule proposal locally. It sends each message to the canonical Huume SSE endpoint and renders the persisted response.

## Required tests

### Pure/unit tests

- Schedule tool declarations equal the schedule allow-list and exclude unrelated Huume tools.
- The schedule prompt is conversational and instructs Huume to inspect before broad answers.
- Schedule surface does not require the generic Matcha Work action feature gate.
- Generic Huume actions continue to require Matcha Work authorization.
- A location-authorized employee manager can confirm schedule actions.
- Malformed UUIDs, blank notes, missing waiver state, invalid dates, and incomplete eligibility acknowledgements are rejected before execution.
- Eligibility `keep` requires confirmation and a written acknowledgement.

### Integration tests

- A session is reused for the same manager/location/week and differs for a different location or week.
- A non-manager and a manager at another location receive 403/404 as appropriate.
- A schedule thread is hidden from generic workspace listing but accepts the session owner’s messages.
- Overview returns only the selected location and seven-day editor window.
- Schedule tool calls cannot escape the session location or use unavailable tools/lookups.
- Note, waiver, permit, remove, and keep writers create correct audit data and preserve transaction safety.
- Digest sends manager/employee content once per day and safely retries delivery failures.

### Frontend tests

- Opening the assistant hydrates a session and shows persisted history.
- Sending a message uses `sendMessageStream`, shows tool timeline/status, and replaces the optimistic message with the persisted response.
- Switching location or week resets the panel and loads the new scoped session.
- A completed successful write invokes schedule reload.

## Verification commands

```bash
cd server
pytest -q tests/huume/test_huume_actions.py tests/huume/test_huume_schedule_skill.py tests/huume/test_schedule_surface.py tests/huume/test_schedule_action_envelope.py tests/employee_schedule/test_shift_compliance.py --disable-warnings
python3 -m compileall -q alembic/versions/huumesched01_schedule_assistant_sessions.py app/matcha/services/huume app/matcha/services/scheduling

cd ../client
npm test -- --run src/ops/pages/ScheduleEditor.test.tsx src/components/employees/schedule-editor/ScheduleChatPanel.test.tsx
npm run build
```

## Rollout checklist

1. Apply Alembic heads, including the Huume dependency migration.
2. Enable `employee_schedule`, `huume`, and the relevant product entitlement for the pilot company.
3. Enable `schedule_daily_digest` only after recipient/content review.
4. Exercise a manager session at one location, a different manager/location, and an unauthorized employee.
5. Verify a staged note, confirmed note, waiver, permit, eligibility remove, and acknowledged retention in audit logs.
