import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { HuumeAction, HuumeActionSendOffer } from '../../../types'
import { actionIcon, DONE_LABELS } from '../../../utils/huumeActionMeta'

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
  }
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
    </div>
  )
}
