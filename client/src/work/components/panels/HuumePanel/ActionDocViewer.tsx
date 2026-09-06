import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import type {
  HuumeAction, HuumeActionScheduleLocationProfile, HuumeActionScheduleWeekDraft,
  HuumeActionSendOffer,
} from '../../../types'
import { actionIcon, DONE_LABELS } from '../../../utils/huumeActionMeta'
import { fmtDayLabel, fmtTime, WEEKDAY_LABELS } from '../../../../types/employeeSchedule'

interface ActionDocViewerProps {
  action: Exclude<HuumeAction, HuumeActionSendOffer>
  lightMode?: boolean
}

function Meta({ label, value }: { label: string; value?: string | number | null }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide opacity-50">{label}</div>
      <div className="text-xs">{value}</div>
    </div>
  )
}

function Prose({ children }: { children?: string | null }) {
  if (!children) return null
  return <p className="max-w-[65ch] whitespace-pre-wrap text-sm leading-relaxed">{children}</p>
}

type WeekFinding = NonNullable<HuumeActionScheduleWeekDraft['findings']>[number]

/** Plain-English heading per finding kind. An unknown kind falls back to the
 *  server's own `detail` line under a generic heading rather than vanishing —
 *  a new backend finding must never render as an empty section. */
const FINDING_LABELS: Record<string, string> = {
  coverage_gap: 'Floor uncovered while open',
  open_buffer_uncovered: 'Nobody for the opening prep',
  close_buffer_uncovered: 'Nobody scheduled to close',
  break_relief_uncovered: 'No cover for a required break',
  break_relief_impossible: 'A required break cannot be scheduled',
  break_relief_thin: 'Floor drops during breaks',
  break_window_conflict: 'Break falls outside its legal window',
  break_rules_unmapped: 'Break rules unavailable',
  break_rules_unresolved: 'Break requirements not evaluated',
  leader_absent_at_open: 'No lead at open',
  leader_absent_at_close: 'No lead at close',
  thin_open: 'Thin at open',
  thin_close: 'Thin at close',
  demand_outside_hours: 'Shift outside opening hours',
  demand_on_closed_day: 'Shift on a closed day',
  no_hours_known: 'Day not checked',
}

function findingRowLabel(finding: WeekFinding): string {
  const day = finding.day ? fmtDayLabel(finding.day) : null
  const window = finding.window ? `${finding.window.start}–${finding.window.end}` : null
  return [day, window].filter(Boolean).join(' · ')
}

/** Everything the generated week does NOT cover, grouped by kind.
 *
 *  Deliberately its own section rather than lines appended to the summary:
 *  "18/18 positions filled" is the number a manager acts on, and a hole at
 *  close has to be visible in the same glance or the card reads as done. */
function NeedsReview(
  { findings, hoursKnown, chipRed }: {
    findings?: WeekFinding[]
    hoursKnown?: boolean
    chipRed: string
  },
) {
  const grouped = new Map<string, WeekFinding[]>()
  for (const finding of findings ?? []) {
    const existing = grouped.get(finding.kind)
    if (existing) existing.push(finding)
    else grouped.set(finding.kind, [finding])
  }
  if (!grouped.size && hoursKnown !== false) return null
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wide opacity-50">Needs review</div>
      {hoursKnown === false && (
        <p className="mb-1.5 text-[11px] opacity-60">
          This location&rsquo;s opening hours are not saved, so coverage at open and close was not checked.
        </p>
      )}
      <div className="space-y-2">
        {[...grouped.entries()].map(([kind, items]) => (
          <div key={kind}>
            <div className="mb-0.5 text-[11px] font-medium opacity-80">
              {FINDING_LABELS[kind] ?? 'Needs a look'}
            </div>
            <div className="space-y-1">
              {items.map((finding, index) => (
                <div
                  key={`${kind}-${index}`}
                  className={
                    finding.severity === 'gap'
                      ? `rounded border px-2 py-1.5 text-[11px] ${chipRed}`
                      : 'rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-600 dark:text-amber-300'
                  }
                >
                  {findingRowLabel(finding) ? `${findingRowLabel(finding)} — ` : ''}
                  {finding.detail}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function titleFor(action: ActionDocViewerProps['action']): string {
  switch (action.type) {
    case 'discipline_draft':
      return `Progressive Discipline${action.infraction_type ? ` — ${action.infraction_type}` : ''}${action.employee_name ? ` · ${action.employee_name}` : ''}`
    case 'ir_report':
      return `Incident Report${action.incident_type ? ` — ${action.incident_type}` : ''}`
    case 'er_case':
      return `ER Case${action.title ? ` — ${action.title}` : ''}`
    case 'training_assign':
      return `Training Assignment${action.employee_ids?.length ? ` — ${action.employee_ids.length} employee(s)` : ''}`
    case 'pto_decision':
      return `PTO ${action.decision === 'deny' ? 'Denial' : 'Approval'}`
    case 'amend_handbook':
      return `Amend Handbook${action.handbook_title ? ` — ${action.handbook_title}` : ''}`
    case 'discipline_from_incident':
      return `Disciplinary Action${action.infraction_type ? ` — ${action.infraction_type}` : ''}${action.employee_name ? ` · ${action.employee_name}` : ''}`
    case 'discipline_decision':
      return `Discipline ${action.decision === 'deny' ? 'Denial' : 'Approval'}`
    case 'ems_promote':
      return `Promote to Incident${action.incident_type ? ` — ${action.incident_type}` : ''}`
    case 'inventory_movement': {
      const verbs: Record<string, string> = {
        in: 'Stock In', out: 'Stock Out', stockout: 'Stockout', adjust: 'Count Adjustment',
      }
      const label = action.new_item_name ?? action.item_id
      return `${verbs[action.kind] ?? 'Stock Movement'}${label ? ` — ${label}` : ''}`
    }
    case 'inventory_order_decision':
      return `Order ${action.decision === 'approve' ? 'Approval' : action.decision === 'receive' ? 'Receipt' : 'Cancellation'}`
    case 'inventory_item_create':
      return `New Inventory Item — ${action.name}`
    case 'inventory_item_archive':
      return 'Archive Inventory Item'
    case 'inventory_receipt':
      return `Receipt Commit${action.vendor ? ` — ${action.vendor}` : ''}`
    case 'schedule_note':
      return 'Assignment Note'
    case 'meal_break_waiver':
      return 'Meal-Break Waiver'
    case 'work_permit':
      return 'Work Permit'
    case 'eligibility_case_decision':
      return 'Eligibility Decision'
    case 'schedule_change':
      return `Schedule Change${action.target_employee_name ? ` — ${action.target_employee_name}` : ''}`
    case 'schedule_week_draft':
      return 'Generated Weekly Schedule'
    case 'schedule_location_profile':
      return 'Location Schedule Profile'
  }
}

/** The server's own "08:00–17:00" for a day the interview covered, "Closed"
 * for an explicit null, "—" for a weekday it never reached. The three cases
 * read differently on purpose: an unanswered day is not a claim that the
 * store is shut. */
function hoursLabel(hours: HuumeActionScheduleLocationProfile['operating_hours'], weekday: number): string {
  if (!hours || !(String(weekday) in hours)) return '—'
  const day = hours[String(weekday)]
  if (!day) return 'Closed'
  return `${day.open}–${day.close}`
}

/** Renders the 5 non-offer staged actions as readable documents instead of
 * compact label/value rows — they already carry their text inline in
 * current_state, so this is pure presentation (no fetch). */
export default function ActionDocViewer({ action, lightMode }: ActionDocViewerProps) {
  const chipEmerald = lightMode ? 'bg-emerald-50 text-emerald-700 border-emerald-300' : 'bg-emerald-950/40 text-emerald-300 border-emerald-800'
  const chipRed = lightMode ? 'bg-red-50 text-red-700 border-red-300' : 'bg-red-950/40 text-red-300 border-red-800'

  const doneLabel = DONE_LABELS[action.type]?.[action.status]

  return (
    <div className="flex w-full flex-1 flex-col gap-3 overflow-y-auto p-4">
      <div className="flex items-center gap-2">
        {actionIcon(action.type, 16)}
        <h3 className="text-sm font-semibold">{titleFor(action)}</h3>
      </div>

      {doneLabel && (
        <div className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded border w-fit ${chipEmerald}`}>
          <CheckCircle2 size={12} /> {doneLabel}
        </div>
      )}
      {action.status === 'failed' && (
        <div className={`flex items-center gap-1.5 text-[11px] px-2 py-1.5 rounded border w-fit ${chipRed}`}>
          <AlertTriangle size={12} /> The last action failed — ask Huume what happened.
        </div>
      )}

      {action.type === 'discipline_draft' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Employee" value={action.employee_name} />
            <Meta label="Severity" value={action.severity ?? 'moderate'} />
            <Meta label="Occurred" value={action.occurrence_dates?.join(', ')} />
          </div>
          <Prose>{action.description}</Prose>
          {action.expected_improvement && (
            <div>
              <div className="text-[10px] uppercase tracking-wide opacity-50">Expected improvement</div>
              <Prose>{action.expected_improvement}</Prose>
            </div>
          )}
        </>
      )}

      {action.type === 'ir_report' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Occurred" value={action.occurred_at} />
            <Meta label="Type" value={action.incident_type} />
            <Meta label="Severity" value={action.severity} />
            <Meta label="Location" value={action.location} />
          </div>
          <Prose>{action.description}</Prose>
        </>
      )}

      {action.type === 'er_case' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Category" value={action.category} />
          </div>
          <Prose>{action.description}</Prose>
          <p className="text-[11px] opacity-60">Involved employees are added on the ER page — never inferred here.</p>
        </>
      )}

      {action.type === 'training_assign' && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Meta label="Requirement" value={action.requirement_id} />
          <Meta label="Employees" value={action.employee_ids?.length} />
          <Meta label="Due" value={action.due_date} />
        </div>
      )}

      {action.type === 'pto_decision' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Request" value={action.request_id} />
            <Meta label="Decision" value={action.decision === 'deny' ? 'Deny' : 'Approve'} />
          </div>
          <Prose>{action.note}</Prose>
        </>
      )}

      {action.type === 'amend_handbook' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Handbook" value={action.handbook_title ?? action.target_handbook_id} />
            <Meta label="Sections/policies" value={action.draft_ids?.length} />
          </div>
          <p className="text-[11px] opacity-60">This edits the live handbook's sections in place — confirm before proceeding.</p>
        </>
      )}

      {action.type === 'discipline_from_incident' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Employee" value={action.employee_name} />
            <Meta label="Severity" value={action.severity ?? 'moderate'} />
            <Meta label="Level" value={action.discipline_type} />
            <Meta label="Occurred" value={action.occurrence_dates?.join(', ')} />
            <Meta label="Template" value={action.template_name} />
          </div>
          <Prose>{action.description}</Prose>
          {action.expected_improvement && (
            <div>
              <div className="text-[10px] uppercase tracking-wide opacity-50">Expected improvement</div>
              <Prose>{action.expected_improvement}</Prose>
            </div>
          )}
          {action.rendered_preview && (
            <div>
              <div className="text-[10px] uppercase tracking-wide opacity-50">Letter preview</div>
              <Prose>{action.rendered_preview}</Prose>
            </div>
          )}
          {!!action.missing_fields?.length && (
            <div className={`flex items-start gap-1.5 text-[11px] px-2 py-1.5 rounded border w-fit ${chipRed}`}>
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              <span>Missing on file: {action.missing_fields.join(', ')} — the letter will read generically for these.</span>
            </div>
          )}
          <p className="text-[11px] opacity-60">This goes to HR approval — nothing is issued until an approver decides.</p>
        </>
      )}

      {action.type === 'discipline_decision' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Record" value={action.record_id} />
            <Meta label="Decision" value={action.decision === 'deny' ? 'Deny' : 'Approve'} />
          </div>
          <Prose>{action.reason}</Prose>
        </>
      )}

      {action.type === 'ems_promote' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Occurred" value={action.occurred_at} />
            <Meta label="Type" value={action.incident_type} />
            <Meta label="Severity" value={action.severity} />
            <Meta label="Location" value={action.location} />
          </div>
          <Prose>{action.title}</Prose>
          <p className="text-[11px] opacity-60">Files the logged event as a real IR incident — the original event stays in Ops.</p>
        </>
      )}

      {action.type === 'inventory_movement' && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Meta label="Item" value={action.new_item_name ?? action.item_id} />
          <Meta label="Kind" value={action.kind} />
          <Meta label="Quantity" value={action.quantity} />
          <Meta label="Note" value={action.note} />
        </div>
      )}

      {action.type === 'inventory_order_decision' && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Meta label="Order" value={action.order_id} />
          <Meta label="Decision" value={action.decision} />
          <Meta label="Quantity" value={action.quantity} />
        </div>
      )}

      {action.type === 'inventory_item_create' && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Meta label="Name" value={action.name} />
          <Meta label="Unit" value={action.unit} />
          <Meta label="Initial qty" value={action.initial_quantity} />
          <Meta label="Low-stock at" value={action.low_stock_threshold} />
        </div>
      )}

      {action.type === 'inventory_item_archive' && (
        <Meta label="Item" value={action.item_id} />
      )}

      {action.type === 'inventory_receipt' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Vendor" value={action.vendor} />
            <Meta label="Invoice" value={action.invoice_number} />
            <Meta label="Lines" value={action.lines.length} />
          </div>
          {action.dup_warning && (
            <div className={`flex items-start gap-1.5 text-[11px] px-2 py-1.5 rounded border w-fit ${chipRed}`}>
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              <span>{action.dup_warning}</span>
            </div>
          )}
        </>
      )}

      {action.type === 'schedule_change' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Employee" value={action.target_employee_name} />
            <Meta label="Date" value={action.target_date ?? action.new_date ?? action.date} />
          </div>
          <Prose>{action.pill_text}</Prose>
        </>
      )}

      {action.type === 'schedule_week_draft' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Week of" value={action.week_start} />
            <Meta label="Demand source" value={action.source_mode === 'template' ? 'Saved template' : 'Existing draft shifts'} />
            {action.auto_generated && <Meta label="Prepared" value="Automatically by Huume" />}
            <Meta label="Shifts" value={action.metrics?.shift_count} />
            <Meta label="Positions filled" value={action.metrics?.filled_positions} />
            <Meta label="Positions needed" value={action.metrics?.required_positions} />
            <Meta label="Still open" value={action.metrics?.open_positions} />
          </div>
          <Prose>{action.summary}</Prose>
          <NeedsReview
            findings={action.findings}
            hoursKnown={action.metrics?.operating_hours_known}
            chipRed={chipRed}
          />
          {!!action.schedule_preview?.length && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide opacity-50">Proposed shifts</div>
              <div className="space-y-1.5">
                {action.schedule_preview.map((shift) => (
                  <div key={shift.shift_key} className="rounded border border-current/10 px-2 py-1.5 text-[11px]">
                    <div className="font-medium">
                      {fmtDayLabel(shift.starts_at)} · {fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}
                      {shift.role ? ` · ${shift.role}` : ''}
                    </div>
                    <div className="mt-0.5 opacity-65">
                      {shift.assignment_names.length
                        ? shift.assignment_names.join(', ')
                        : 'Open'} · {shift.assignment_names.length}/{shift.required_staff} staffed
                    </div>
                  </div>
                ))}
              </div>
              {action.preview_truncated && (
                <p className="mt-1 text-[10px] opacity-50">Additional shifts are saved in this proposal and will appear in the editor after confirmation.</p>
              )}
            </div>
          )}
          {!!action.unfilled?.length && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide opacity-50">Open positions</div>
              <div className="space-y-1">
                {action.unfilled.map((item, index) => (
                  <div key={`${item.shift_key ?? 'shift'}-${index}`} className={`rounded border px-2 py-1.5 text-[11px] ${chipRed}`}>
                    {item.starts_at ? `${fmtDayLabel(item.starts_at)} · ${fmtTime(item.starts_at)}` : 'Shift'}
                    {item.role ? ` · ${item.role}` : ''} — {item.reason ?? 'No eligible employee'}
                  </div>
                ))}
              </div>
            </div>
          )}
          <p className="text-[11px] opacity-60">Confirmation adds this proposal to the editor as drafts. Review or edit it there, then publish when ready.</p>
        </>
      )}

      {action.type === 'schedule_location_profile' && (
        <>
          <Prose>{action.summary}</Prose>
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide opacity-50">Operating hours</div>
            <div className="space-y-0.5">
              {WEEKDAY_LABELS.map((dayLabel, weekday) => (
                <div key={dayLabel} className="flex items-baseline gap-3 text-[11px]">
                  <span className="w-8 shrink-0 opacity-65">{dayLabel}</span>
                  <span>{hoursLabel(action.operating_hours, weekday)}</span>
                </div>
              ))}
            </div>
          </div>
          {!!action.blocks?.length && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide opacity-50">Staffing blocks</div>
              <div className="space-y-1.5">
                {action.blocks.map((block, index) => (
                  <div key={`${block.name}-${index}`} className="rounded border border-current/10 px-2 py-1.5 text-[11px]">
                    <div className="font-medium">{block.name} · {block.job_name}</div>
                    <div className="mt-0.5 opacity-65">
                      {block.days_of_week.map((weekday) => WEEKDAY_LABELS[weekday] ?? '?').join(', ') || 'No days set'}
                      {' · '}{block.start_time}–{block.end_time} · ×{block.required_staff}
                      {block.break_minutes ? ` · ${block.break_minutes}m break` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Leader on shift" value={action.leader_job_name} />
            <Meta label="Template" value={action.template_name} />
          </div>
          {action.notes && (
            <div>
              <div className="text-[10px] uppercase tracking-wide opacity-50">Notes</div>
              <Prose>{action.notes}</Prose>
            </div>
          )}
          <p className="text-[11px] opacity-60">Confirmation saves this as the location's scheduling setup — it doesn't create any shifts on its own.</p>
        </>
      )}

      {action.type === 'schedule_note' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Employee" value={action.employee_id} />
            <Meta label="Shift" value={action.shift_id} />
          </div>
          <Prose>{action.note}</Prose>
        </>
      )}

      {action.type === 'meal_break_waiver' && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Meta label="Employee" value={action.employee_id} />
            <Meta label="On file" value={action.on_file ? 'Yes' : 'No'} />
            <Meta label="Effective" value={action.effective_from} />
          </div>
          <Prose>{action.note}</Prose>
        </>
      )}

      {action.type === 'work_permit' && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Meta label="Employee" value={action.employee_id} />
          <Meta label="Issued" value={action.issued_at} />
          <Meta label="Expires" value={action.expires_at} />
        </div>
      )}

      {action.type === 'eligibility_case_decision' && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Meta label="Case" value={action.case_id} />
          <Meta label="Decision" value={action.decision} />
          <Meta label="Acknowledgement" value={action.acknowledgement_note} />
        </div>
      )}
    </div>
  )
}
