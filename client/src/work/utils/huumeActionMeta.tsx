import { CalendarCheck, FileSignature, GraduationCap, Scale, ShieldAlert, Siren } from 'lucide-react'
import type { HuumeAction } from '../types'

/** Terminal status -> the past-tense chip. Keyed by type because each staged
 * action writes its own done word (see _HR_OPS_TOOL_SPECS in agent.py);
 * 'failed'/'cancelled' are handled before this map is consulted. Shared by
 * the chat banner (HuumeActionCard), the panel's ConfirmBar, and
 * ActionDocViewer. */
export const DONE_LABELS: Record<string, Record<string, string>> = {
  send_offer: { sent: 'Offer sent' },
  discipline_draft: { filed: 'Write-up filed' },
  ir_report: { filed: 'Incident filed' },
  er_case: { opened: 'ER case opened' },
  training_assign: { assigned: 'Training assigned' },
  pto_decision: { decided: 'PTO decision applied' },
}

/** One-line summary for the banner strip / the panel's docked ConfirmBar. */
export function bannerLabel(action: HuumeAction): string {
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

/** Icon for a staged action's type — shared by the banner strip, the panel
 * header tabs, and ActionDocViewer's title row. */
export function actionIcon(type: HuumeAction['type'], size = 14) {
  if (type === 'send_offer') return <FileSignature size={size} />
  if (type === 'ir_report') return <Siren size={size} />
  if (type === 'er_case') return <Scale size={size} />
  if (type === 'training_assign') return <GraduationCap size={size} />
  if (type === 'pto_decision') return <CalendarCheck size={size} />
  return <ShieldAlert size={size} />
}
