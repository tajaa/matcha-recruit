# Full Schedule Editor Plan

## Scope Decisions

- Build a dedicated full-week editor at `/ops/schedule/editor?week=YYYY-MM-DD`.
- Autosave each successful change to the existing durable draft records.
- Keep publishing explicit through `Publish week`.
- Support dragging shifts, roster employees, and existing assignments.
- Published shifts are locked by default and require an explicit `Edit published schedule` toggle.
- Reuse existing conflict, availability, training, compliance, audit, and Fair Workweek rules.
- Do not add a database migration or scenario/version table.

## Editor UX

The editor has three primary regions:

| Region | Behavior |
| --- | --- |
| Roster panel | Search/filter employees; drag employees onto existing shifts or empty time slots. |
| Week grid | Seven-day, 24-hour timeline with 15-minute snapping and horizontally scrollable mobile layout. |
| Inspector | Exact date/time, role, department, location, break, staffing, notes, training type, status, delete/cancel. |

Toolbar controls:

- Previous week, next week, this week
- Draft/published visibility filters
- Autosave status: `Saving draft...`, `Draft saved`, or `Save failed`
- `Edit published schedule` safety toggle
- `Publish week (N)`
- Back to standard Schedule view

Drag behavior:

| Source | Destination | Result |
| --- | --- | --- |
| Roster employee | Existing shift | Assign employee. |
| Roster employee | Empty time slot | Open a new draft inspector with the employee preselected. |
| Existing assignment | Another shift | Atomically move the assignment. |
| Existing assignment | Unassign zone | Remove the assignment. |
| Shift handle | Time slot | Move the shift while preserving duration. |
| Shift resize handle | New end time | Change duration in 15-minute increments. |
| Empty time slot click | Inspector | Create an unassigned draft shift. |

Every drag interaction has a click/keyboard fallback.

## Backend

### Assignment Move Model

Modify `server/app/matcha/models/scheduling/employee_schedule.py`:

```python
class AssignmentMove(BaseModel):
    employee_id: UUID
    from_shift_id: UUID
    to_shift_id: UUID

    @model_validator(mode="after")
    def _different_shifts(self) -> "AssignmentMove":
        if self.from_shift_id == self.to_shift_id:
            raise ValueError("source and destination shifts must differ")
        return self
```

### Transactional Move Endpoint

Modify `server/app/matcha/routes/employee_schedule/assignments.py`:

```python
@router.post("/assignments/move")
async def move_employee_assignment(
    body: AssignmentMove,
    force: bool = Query(False),
    current_user=Depends(require_admin_or_client),
) -> dict:
    ...
```

Endpoint response:

```json
{
  "source_shift": { "...": "Shift" },
  "target_shift": { "...": "Shift" }
}
```

Required semantics:

1. Resolve and tenant-scope both shifts.
2. Lock both shift rows in deterministic ID order.
3. Reject identical source and destination shifts.
4. Reject missing or cancelled shifts.
5. Verify the employee belongs to the tenant and remains schedulable.
6. Verify the employee is assigned to the source.
7. Reject if already assigned to the destination.
8. Check destination headcount.
9. Check conflicts while excluding the source shift.
10. Check destination availability and scheduling compliance.
11. Check source unassignment Fair Workweek advisories.
12. Allow `force=true` for overlap, capacity, availability, and advisory violations.
13. Never allow `force=true` to bypass hard compliance blocks.
14. Remove from source and add to destination in one transaction.
15. Reuse `remove_assignment_core()` and `apply_assignment_core()`.
16. Preserve existing audit action names:
    - `assignment.delete`
    - `assignment.create`
17. Add audit context:

```python
{
    "source": "schedule_editor_move",
    "from_shift_id": str(body.from_shift_id),
    "to_shift_id": str(body.to_shift_id),
}
```

If any target write fails, the transaction preserves the original source assignment.

### Schedule Locations

The full inspector needs location names without depending on a separate Compliance-page fetch.

Modify `server/app/matcha/routes/employee_schedule/_shared.py`:

```python
async def fetch_schedule_locations(conn, company_id: UUID) -> list[dict]:
    ...
```

Return:

```python
{
    "id": str,
    "name": str | None,
    "city": str,
    "state": str,
    "is_active": bool,
}
```

Modify `server/app/matcha/routes/employee_schedule/shifts.py:get_week()` to include `locations`.

Inactive locations remain in the response so existing shifts can display their historical location, but they are disabled for new shifts.

### Backend Tests

Add `server/tests/employee_schedule/test_assignment_move.py` using fake asyncpg connections and dependency monkeypatching, not a live database.

Cases:

1. Move removes the source assignment and creates the target assignment atomically.
2. Missing source assignment returns `409`.
3. Cancelled destination returns `409`.
4. Employee already assigned to destination returns `409`.
5. Source shift is excluded from overlap detection.
6. A third overlapping shift still causes `schedule_conflict`.
7. Full destination returns `shift_full`.
8. `force=true` permits a full destination.
9. Outside availability returns `outside_availability`.
10. Hard compliance block remains non-forceable.
11. Source Fair Workweek advisory is forceable.
12. Failed target validation produces no write or audit rows.
13. Both audit rows use existing action names and editor context.
14. Tenant mismatch returns `404`.

Extend `server/tests/employee_schedule/test_schedule_models.py`:

1. Valid `AssignmentMove`.
2. Same source and destination rejected.
3. Invalid UUID rejected.

No live DB-mutating test runs automatically.

## Frontend API And Types

### Types

Modify `client/src/types/employeeSchedule.ts`:

```typescript
export interface ScheduleLocation {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

export interface AssignmentMovePayload {
  employee_id: string
  from_shift_id: string
  to_shift_id: string
}

export interface AssignmentMoveResponse {
  source_shift: Shift
  target_shift: Shift
}
```

Add `locations: ScheduleLocation[]` to `WeekResponse`.

### API

Modify `client/src/api/employees/employeeSchedule.ts`:

```typescript
export function moveAssignment(
  payload: AssignmentMovePayload,
  force = false,
): Promise<AssignmentMoveResponse>
```

Endpoint:

```text
POST /employee-schedule/assignments/move?force=true|false
```

Existing APIs remain authoritative for `createShift`, `updateShift`, `deleteShift`, `assignEmployee`, `unassignEmployee`, and `publishRange`.

## Editor State

Add `client/src/hooks/employees/useScheduleEditor.ts`.

Proposed interface:

```typescript
export type ScheduleSaveState = 'idle' | 'saving' | 'saved' | 'error'

export function useScheduleEditor(weekStart: string): {
  shifts: Shift[]
  roster: RosterEmployee[]
  rosterFlags: RosterFlags | null
  locations: ScheduleLocation[]
  summary: ScheduleSummary | null
  loading: boolean
  saveState: ScheduleSaveState
  lastSavedAt: Date | null
  pendingKeys: ReadonlySet<string>

  reload(): Promise<void>

  createDraft(payload: ShiftPayload): Promise<Shift | null>
  updateShiftDraft(shift: Shift, payload: Partial<ShiftPayload>): Promise<Shift | null>
  moveShift(shift: Shift, targetDate: string, targetMinute: number): Promise<Shift | null>
  resizeShift(shift: Shift, endMinute: number): Promise<Shift | null>
  assignToShift(shift: Shift, employeeId: string): Promise<Shift | null>
  moveEmployee(
    employeeId: string,
    fromShiftId: string,
    toShiftId: string,
  ): Promise<AssignmentMoveResponse | null>
  unassignFromShift(shift: Shift, employeeId: string): Promise<Shift | null>
  removeShift(shift: Shift): Promise<boolean>
  publishWeek(): Promise<void>
}
```

Mutation behavior:

- Do not optimistically alter persisted state.
- Mark the affected card as saving.
- Execute the API call.
- If `conflictPrompt()` recognizes a forceable `409`, confirm and retry with `force=true`.
- On success, patch returned shifts into local state.
- On cancellation, leave state unchanged.
- On non-forceable errors, show a toast and reload the week to remove stale state.
- Ignore stale responses after the manager changes weeks.
- Serialize mutations affecting the same shift.
- Permit independent shifts to save concurrently.

Published-shift protection:

```typescript
function canMutateShift(
  shift: Shift,
  editPublished: boolean,
): boolean
```

Draft shifts are always editable. Published shifts require the toggle. Cancelled shifts cannot accept assignments or drag operations.

## Drag Model

Add `client/src/components/employees/schedule-editor/drag.ts`.

```typescript
export type ScheduleDragData =
  | { kind: 'roster-employee'; employeeId: string }
  | { kind: 'shift-assignment'; employeeId: string; fromShiftId: string }
  | { kind: 'shift'; shiftId: string }

export type ScheduleDropData =
  | { kind: 'shift'; shiftId: string }
  | { kind: 'time-slot'; date: string; minute: number }
  | { kind: 'unassign' }

export type ScheduleDropAction =
  | { kind: 'assign'; employeeId: string; toShiftId: string }
  | { kind: 'move-assignment'; employeeId: string; fromShiftId: string; toShiftId: string }
  | { kind: 'unassign'; employeeId: string; fromShiftId: string }
  | { kind: 'move-shift'; shiftId: string; date: string; minute: number }
  | { kind: 'create-with-employee'; employeeId: string; date: string; minute: number }

export function resolveScheduleDrop(
  active: ScheduleDragData,
  over: ScheduleDropData | null,
): ScheduleDropAction | null
```

Use the existing dependencies from `client/package.json`:

```typescript
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
```

Sensors:

- Pointer: 8-pixel activation distance
- Touch: short hold with movement tolerance
- Keyboard: enabled for draggable controls
- Announcements describe assignment and move results

## Calendar Math

Add `client/src/components/employees/schedule-editor/calendarMath.ts`.

```typescript
export const SLOT_MINUTES = 15
export const MIN_SHIFT_MINUTES = 15
export const MAX_SHIFT_MINUTES = 24 * 60

export function snapMinute(minute: number, interval?: number): number

export function shiftDurationMinutes(
  shift: Pick<Shift, 'starts_at' | 'ends_at'>,
): number

export function moveShiftWindow(
  shift: Pick<Shift, 'starts_at' | 'ends_at'>,
  targetDate: string,
  targetMinute: number,
): Pick<ShiftPayload, 'starts_at' | 'ends_at'>

export function resizeShiftWindow(
  shift: Pick<Shift, 'starts_at' | 'ends_at'>,
  endMinute: number,
): Pick<ShiftPayload, 'ends_at'>

export function shiftPosition(
  shift: Pick<Shift, 'starts_at' | 'ends_at'>,
): {
  topPercent: number
  heightPercent: number
  continuesNextDay: boolean
}

export function layoutOverlappingShifts(
  shifts: Shift[],
): Array<{ shift: Shift; lane: number; laneCount: number }>
```

Rules:

- Keep the existing UTC wall-clock behavior.
- Moving preserves exact duration.
- Moving an overnight shift preserves its overnight duration.
- Drag targets snap to 15 minutes.
- Inspector inputs retain exact minute editing.
- Resize cannot produce zero or negative duration.
- Overnight blocks render on their start day with a `continues next day` marker.

## Components

### Page

Add `client/src/ops/pages/ScheduleEditor.tsx`.

Responsibilities:

- Parse the `week` query parameter.
- Mount `useScheduleEditor`.
- Own `editPublished` state.
- Own active drag state and drag overlay.
- Dispatch `ScheduleDropAction` to the hook.
- Render toolbar, roster, grid, and inspector.
- Use `p-3 md:p-5` so content never touches the Ops sidebar.

### Toolbar

Add `client/src/components/employees/schedule-editor/ScheduleEditorToolbar.tsx`.

```typescript
interface ScheduleEditorToolbarProps {
  weekStart: string
  summary: ScheduleSummary | null
  saveState: ScheduleSaveState
  lastSavedAt: Date | null
  editPublished: boolean
  publishing: boolean
  onPreviousWeek(): void
  onNextWeek(): void
  onThisWeek(): void
  onTogglePublishedEditing(value: boolean): void
  onPublish(): void
  onExit(): void
}
```

### Roster

Add `client/src/components/employees/schedule-editor/RosterPanel.tsx`.

```typescript
interface RosterPanelProps {
  roster: RosterEmployee[]
  rosterFlags: RosterFlags | null
  selectedEmployeeId: string | null
  onSelectEmployee(employeeId: string | null): void
}
```

Behavior:

- Search by name, role, and department.
- Show training and credential warning counts.
- Desktop sticky left panel.
- Mobile collapsible top drawer.
- Employee rows are draggable and keyboard-selectable.

### Grid

Add `client/src/components/employees/schedule-editor/WeekTimeGrid.tsx`.

```typescript
interface WeekTimeGridProps {
  days: string[]
  shifts: Shift[]
  pendingKeys: ReadonlySet<string>
  editPublished: boolean
  selectedEmployeeId: string | null
  onCreateAt(date: string, minute: number, employeeId?: string): void
  onOpenShift(shift: Shift): void
  onAssignSelected(shift: Shift): void
  onResizeShift(shift: Shift, endMinute: number): void
}
```

Behavior:

- Sticky day headers and time gutter.
- Seven columns and 15-minute rows.
- Horizontal scroll below desktop width.
- Concurrent shifts receive separate lanes.
- Empty cells open the new-shift inspector.
- Selected employees can be assigned by clicking a shift.

### Shift Block

Add `client/src/components/employees/schedule-editor/ShiftBlock.tsx`.

```typescript
interface ShiftBlockProps {
  shift: Shift
  pending: boolean
  editPublished: boolean
  selectedEmployeeId: string | null
  lane: number
  laneCount: number
  onOpen(): void
  onAssignSelected(): void
  onResize(endMinute: number): void
}
```

Visual states:

- Draft, published, and cancelled
- Open staffing slots
- Fully staffed
- Drag-over assignment target
- Saving
- Published locked
- Compliance/training lapse indicator
- Overnight continuation

Use a dedicated shift drag handle so nested assignment chips can drag independently.

### Inspector

Add `client/src/components/employees/schedule-editor/ShiftInspector.tsx`.

```typescript
export type NewShiftDefaults = {
  date: string
  minute: number
  employeeIds?: string[]
}

interface ShiftInspectorProps {
  shift: Shift | null
  defaults: NewShiftDefaults | null
  locations: ScheduleLocation[]
  roster: RosterEmployee[]
  trainingEnabled: boolean
  readOnly: boolean
  saving: boolean
  onCreate(payload: ShiftPayload): Promise<void>
  onUpdate(payload: Partial<ShiftPayload>): Promise<void>
  onDelete(): Promise<void>
  onClose(): void
}
```

Fields:

- Date
- Start and end
- Role
- Department
- Location
- Break minutes
- Required staff
- Notes
- Work/training kind for new shifts
- Training requirement for new training shifts
- Assigned employees
- Draft/published status display

## Routing

Modify `client/src/ops/routes/OpsRoutes.tsx` to use one shared Schedule feature gate:

```tsx
<Route
  element={
    <FeatureGate
      feature="employee_schedule"
      label="Schedule"
      allowPlatformAdmin
    >
      <Outlet />
    </FeatureGate>
  }
>
  <Route path="schedule" element={<EmployeeSchedule />} />
  <Route path="schedule/editor" element={<ScheduleEditor />} />
</Route>
```

Modify `client/src/pages/app/employees/EmployeeSchedule.tsx`:

- Add a `Full shift editor` button.
- Navigate to `/ops/schedule/editor?week=${weekStart}`.
- Keep the existing compact Schedule view for review and quick changes.
- Keep Templates, Requests, and Intelligence tabs unchanged.

`OpsSidebar` already treats `/ops/schedule/editor` as active because its active check uses the `/ops/schedule` prefix.

## Frontend Tests

### Pure Math

Add `client/src/components/employees/schedule-editor/calendarMath.test.ts`.

Cases:

1. Fifteen-minute snapping.
2. Same-day shift movement preserves duration.
3. Cross-day movement preserves duration.
4. Overnight movement keeps the next-day end.
5. Resize respects minimum duration.
6. Resize supports overnight end times.
7. Positioning maps midnight and noon correctly.
8. Overlapping shifts receive separate lanes.
9. Non-overlapping shifts reuse lanes.
10. Three-way overlap calculates a consistent lane count.

### Drop Resolution

Add `client/src/components/employees/schedule-editor/drag.test.ts`.

Cases:

1. Roster employee to shift resolves to assignment.
2. Roster employee to time slot resolves to a new assigned draft.
3. Existing assignment to another shift resolves to move.
4. Existing assignment to the source shift is a no-op.
5. Existing assignment to the unassign zone resolves correctly.
6. Shift to time slot resolves to shift move.
7. Incompatible source/target pairs return `null`.
8. Missing drop target returns `null`.

### Hook

Add `client/src/hooks/employees/useScheduleEditor.test.tsx` and mock the employee-schedule API.

Cases:

1. Loads week, roster, flags, locations, and summary.
2. Shift move calls `updateShift` with preserved duration.
3. Assignment patches only the target shift.
4. Assignment move patches both source and target.
5. Unassignment patches the source.
6. Forceable `409` prompts and retries with `force=true`.
7. Declined force confirmation leaves state unchanged.
8. Hard `422` shows an error and never retries.
9. Failed mutation reloads stale week state.
10. Save state moves through saving, saved, and error.
11. Stale prior-week responses are ignored.
12. Publish replaces returned shifts and summary.

### Component

Add `client/src/ops/pages/ScheduleEditor.test.tsx`.

Cases:

1. Renders seven days and the searchable roster.
2. Clicking an empty slot opens the new-shift inspector.
3. Dropping a roster employee on an empty slot preselects that employee.
4. Published shifts are locked by default.
5. The published editing toggle unlocks them.
6. Cancelled shifts remain non-droppable.
7. Selecting an employee and clicking a shift provides the keyboard fallback.
8. Publish confirmation reports open shifts.
9. Long employee names remain inside shift cards.
10. The mobile roster drawer opens and selects an employee.

Extend `client/src/ops/routes/OpsRoutes.test.tsx` with `/ops/schedule/editor`.

## Documentation

Update `server/app/matcha/services/scheduling/CLAUDE.md` with:

- Full editor route
- Autosaved draft semantics
- Published-shift safety lock
- Transactional assignment moves
- Existing conflict and compliance invariants
- No new schema or scenario entity

## Verification

Run after implementation:

```bash
cd server
python3 -m pytest \
  tests/employee_schedule/test_schedule_models.py \
  tests/employee_schedule/test_assignment_move.py \
  tests/employee_schedule/test_shift_writes.py \
  -v
```

```bash
cd client
npx vitest run \
  src/components/employees/schedule-editor/calendarMath.test.ts \
  src/components/employees/schedule-editor/drag.test.ts \
  src/hooks/employees/useScheduleEditor.test.tsx \
  src/ops/pages/ScheduleEditor.test.tsx \
  src/ops/routes/OpsRoutes.test.tsx
npx tsc -p tsconfig.app.json --noEmit
npx vitest run
```

Also run `git diff --check`.

Manual local verification, not automated because it mutates schedule data:

1. Create a draft by clicking an empty slot.
2. Create a draft by dropping an employee on an empty slot.
3. Move a draft shift across days and times.
4. Resize a draft shift.
5. Assign from the roster.
6. Move an existing assignment between shifts.
7. Trigger overlap, full-shift, availability, advisory, and hard-block behavior.
8. Reload and confirm drafts persisted.
9. Confirm published shifts are locked initially.
10. Publish and confirm portal visibility.
11. Verify expanded/collapsed Ops sidebar at 1440px, 1024px, and mobile widths.

## Non-Goals

- Multiple named schedule scenarios or branches
- Offline editing
- Collaborative real-time cursors
- Bulk unsaved browser-only transactions
- Changing the UTC wall-clock convention
- Replacing templates or employee request workflows
