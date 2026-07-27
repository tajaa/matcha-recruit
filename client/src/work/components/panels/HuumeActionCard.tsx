import { AlertTriangle, CalendarCheck, CheckCircle2, FileSignature, GraduationCap, Scale, ShieldAlert, Siren } from 'lucide-react'
import type { HuumeAction } from '../../types'

interface HuumeActionCardProps {
  action: HuumeAction
  lightMode?: boolean
  /** Disables Confirm/Cancel while a turn is streaming — the staged state may
   * be about to change under the buttons. */
  streaming?: boolean
  /** Sends the literal chat text through the thread's normal send path.
   * Confirm/cancel are chat-only tools by design (services/huume/actions.py
   * evaluate_huume_action): the click still produces a separate user turn,
   * so the backend's structural two-turn confirm rule is fully preserved.
   * No REST twin exists for this. */
  onSendChat?: (text: string) => void
  /** 'panel' = full card inside the Huume right panel; 'banner' = slim strip
   * between the message list and composer (visible on mobile too). */
  variant?: 'panel' | 'banner'
}

function Row({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div className="text-[11px]">
      <span className="opacity-60">{label}: </span>
      <span>{value}</span>
    </div>
  )
}

/** Terminal status -> the past-tense chip. Keyed by type because each staged
 * action writes its own done word (see _HR_OPS_TOOL_SPECS in agent.py);
 * 'failed'/'cancelled' are handled before this map is consulted. */
const DONE_LABELS: Record<string, Record<string, string>> = {
  send_offer: { sent: 'Offer sent' },
  discipline_draft: { filed: 'Write-up filed' },
  ir_report: { filed: 'Incident filed' },
  er_case: { opened: 'ER case opened' },
  training_assign: { assigned: 'Training assigned' },
  pto_decision: { decided: 'PTO decision applied' },
}

/** One-line summary for the banner strip — the full panel card carries the detail. */
function bannerLabel(action: HuumeAction): string {
  switch (action.type) {
    case 'send_offer':
      return 'Send offer for signature?'
    case 'discipline_draft':
      return `Write-up for ${action.employee_name ?? 'employee'} staged — confirm?`
    case 'ir_report':
      return 'File this incident report?'
    case 'er_case':
      return 'Open this ER case?'
    case 'training_assign':
      return `Assign training to ${action.employee_ids?.length ?? 0} employee(s)?`
    case 'pto_decision':
      return `${action.decision === 'deny' ? 'Deny' : 'Approve'} this PTO request?`
    default:
      return 'Action staged — confirm or cancel?'
  }
}

export default function HuumeActionCard({ action, lightMode, streaming, onSendChat, variant = 'panel' }: HuumeActionCardProps) {
  const cardBg = lightMode ? 'bg-orange-50 border-orange-200 text-orange-900' : 'bg-orange-950/30 border-orange-900/50 text-orange-100'
  const chipEmerald = lightMode ? 'bg-emerald-50 text-emerald-700 border-emerald-300' : 'bg-emerald-950/40 text-emerald-300 border-emerald-800'
  const chipRed = lightMode ? 'bg-red-50 text-red-700 border-red-300' : 'bg-red-950/40 text-red-300 border-red-800'

  if (action.status === 'cancelled') return null

  const doneLabel = DONE_LABELS[action.type]?.[action.status]
  if (doneLabel) {
    if (variant === 'banner') return null
    return (
      <div className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded border w-fit ${chipEmerald}`}>
        <CheckCircle2 size={12} /> {doneLabel}
      </div>
    )
  }

  if (action.status === 'failed') {
    return (
      <div className={`flex items-center gap-1.5 text-[11px] px-2 py-1.5 rounded border w-fit ${chipRed}`}>
        <AlertTriangle size={12} /> The last action failed — ask Huume what happened.
      </div>
    )
  }

  // status === 'proposed' — awaiting confirmation.
  let icon = <ShieldAlert size={14} />
  if (action.type === 'send_offer') icon = <FileSignature size={14} />
  else if (action.type === 'ir_report') icon = <Siren size={14} />
  else if (action.type === 'er_case') icon = <Scale size={14} />
  else if (action.type === 'training_assign') icon = <GraduationCap size={14} />
  else if (action.type === 'pto_decision') icon = <CalendarCheck size={14} />

  if (variant === 'banner') {
    return (
      <div className={`mx-3 mt-2 flex items-center gap-2 rounded border px-2.5 py-1.5 ${cardBg}`}>
        {icon}
        <span className="flex-1 truncate text-[11px] font-medium">{bannerLabel(action)}</span>
        <button
          type="button"
          disabled={streaming || !onSendChat}
          onClick={() => onSendChat?.('confirm')}
          className="text-[11px] font-medium px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white"
        >
          Confirm
        </button>
        <button
          type="button"
          disabled={streaming || !onSendChat}
          onClick={() => onSendChat?.('cancel')}
          className="text-[11px] font-medium px-2 py-1 rounded border border-orange-700 text-orange-300 hover:bg-orange-950/40 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Cancel
        </button>
      </div>
    )
  }

  let body: React.ReactNode
  switch (action.type) {
    case 'send_offer':
      body = (
        <>
          <div className="text-[12px] font-medium">Ready to send the offer for signature.</div>
          <Row label="Offer" value={action.offer_id} />
        </>
      )
      break
    case 'discipline_draft':
      body = (
        <>
          <div className="text-[12px] font-medium">Progressive-discipline write-up staged for review.</div>
          <Row label="Employee" value={action.employee_name} />
          <Row label="Type" value={action.infraction_type} />
          <Row label="Severity" value={action.severity ?? 'moderate'} />
          <Row label="Occurred" value={action.occurrence_dates?.join(', ')} />
          {action.description && <div className="text-[11px] line-clamp-3">{action.description}</div>}
          <Row label="Expected improvement" value={action.expected_improvement} />
        </>
      )
      break
    case 'ir_report':
      body = (
        <>
          <div className="text-[12px] font-medium">Incident report staged for the IR log.</div>
          {action.description && <div className="text-[11px] line-clamp-3">{action.description}</div>}
          <Row label="Occurred" value={action.occurred_at} />
          <Row label="Type" value={action.incident_type} />
          <Row label="Severity" value={action.severity} />
          <Row label="Location" value={action.location} />
        </>
      )
      break
    case 'er_case':
      body = (
        <>
          <div className="text-[12px] font-medium">ER case staged.</div>
          <Row label="Title" value={action.title} />
          <Row label="Category" value={action.category} />
          {action.description && <div className="text-[11px] line-clamp-3">{action.description}</div>}
          <div className="text-[10px] opacity-70">Involved employees are added on the ER page — never inferred here.</div>
        </>
      )
      break
    case 'training_assign':
      body = (
        <>
          <div className="text-[12px] font-medium">
            Training assignment staged for {action.employee_ids?.length ?? 0} employee(s).
          </div>
          <Row label="Requirement" value={action.requirement_id} />
          <Row label="Due" value={action.due_date} />
        </>
      )
      break
    case 'pto_decision':
      body = (
        <>
          <div className="text-[12px] font-medium">
            PTO request staged to be {action.decision === 'deny' ? 'denied' : 'approved'}.
          </div>
          <Row label="Request" value={action.request_id} />
          <Row label="Note" value={action.note} />
        </>
      )
      break
    default:
      // Forward-compatible with a future staged action type this UI doesn't
      // know about yet — still surfaces Confirm/Cancel rather than rendering
      // nothing, which is the failure mode this card exists to fix.
      body = <div className="text-[12px] font-medium">An action is staged — reply in chat to confirm or cancel.</div>
  }

  return (
    <div className={`flex flex-col gap-2 rounded border px-3 py-2.5 ${cardBg}`}>
      <div className="flex items-center gap-1.5">{icon}<span className="text-[10px] uppercase tracking-wide opacity-70">Awaiting your confirmation</span></div>
      {body}
      <div className="flex gap-1.5 mt-0.5">
        <button
          type="button"
          disabled={streaming || !onSendChat}
          onClick={() => onSendChat?.('confirm')}
          className="flex-1 text-xs font-medium px-2 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white"
        >
          Confirm
        </button>
        <button
          type="button"
          disabled={streaming || !onSendChat}
          onClick={() => onSendChat?.('cancel')}
          className="flex-1 text-xs font-medium px-2 py-1.5 rounded border border-orange-700 text-orange-300 hover:bg-orange-950/40 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
