import { Archive, ArrowUpCircle, BookOpen, CalendarClock, CalendarCheck, FileSignature, Gavel, GraduationCap, Package, Receipt, Scale, ShieldAlert, Siren, Truck } from 'lucide-react'
import type { HuumeAction } from '../types'

/** Terminal status -> the past-tense chip. Keyed by type because each staged
 * action writes its own done word (see _HR_OPS_TOOL_SPECS in agent.py);
 * 'failed'/'cancelled' are handled before this map is consulted. Shared by
 * the chat banner (HuumeActionCard) and ActionDocViewer. */
export const DONE_LABELS: Record<string, Record<string, string>> = {
  send_offer: { sent: 'Offer sent' },
  discipline_draft: { filed: 'Write-up filed' },
  ir_report: { filed: 'Incident filed' },
  er_case: { opened: 'ER case opened' },
  training_assign: { assigned: 'Training assigned' },
  pto_decision: { decided: 'PTO decision applied' },
  amend_handbook: { amended: 'Handbook amended' },
  discipline_from_incident: { filed: 'Disciplinary action staged for HR approval' },
  discipline_decision: { decided: 'Approval decision recorded' },
  ems_promote: { promoted: 'Promoted to incident' },
  inventory_movement: { recorded: 'Stock movement recorded' },
  inventory_order_decision: { decided: 'Order decision applied' },
  inventory_item_create: { created: 'Item added' },
  inventory_item_archive: { archived: 'Item archived' },
  inventory_receipt: { committed: 'Receipt committed' },
  schedule_change: { applied: 'Schedule updated' },
  schedule_week_draft: { applied: 'Generated week added as drafts' },
  schedule_note: { created: 'Assignment note saved' },
  meal_break_waiver: { created: 'Meal-break waiver recorded' },
  work_permit: { created: 'Work permit recorded' },
  eligibility_case_decision: { created: 'Eligibility decision applied' },
}

/** One-line summary for the chat banner strip / the panel's passive status line. */
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
    case 'amend_handbook':
      return `Amend ${action.handbook_title ?? 'this handbook'} — confirm?`
    case 'discipline_from_incident':
      return `Stage disciplinary action for ${action.employee_name ?? 'employee'} — confirm?`
    case 'discipline_decision':
      return `${action.decision === 'deny' ? 'Deny' : 'Approve'} this disciplinary action?`
    case 'ems_promote':
      return 'Promote this event to an incident?'
    case 'inventory_movement': {
      const label = action.new_item_name ?? 'this item'
      if (action.kind === 'stockout') return `Mark ${label} as out of stock?`
      if (action.kind === 'adjust') return `Set ${label}'s count to ${action.quantity ?? '?'}?`
      const verb = action.kind === 'in' ? 'received' : 'used'
      const qty = action.quantity != null ? `${action.quantity} ` : ''
      return `Record ${qty}${label} ${verb}?`
    }
    case 'inventory_order_decision':
      return `${action.decision === 'approve' ? 'Approve' : action.decision === 'receive' ? 'Mark received' : 'Cancel'} this order?`
    case 'inventory_item_create':
      return `Add "${action.name}" to inventory?`
    case 'inventory_item_archive':
      return 'Archive this inventory item?'
    case 'inventory_receipt':
      return `Commit this receipt (${action.lines.length} line${action.lines.length === 1 ? '' : 's'})?`
    case 'schedule_change':
      return action.pill_text?.split('\n', 1)[0] ?? 'Apply this schedule change?'
    case 'schedule_week_draft': {
      const filled = action.metrics?.filled_positions ?? '?'
      const required = action.metrics?.required_positions ?? '?'
      return `Use this generated week (${filled}/${required} positions filled)?`
    }
    case 'schedule_note':
      return 'Save this assignment note?'
    case 'meal_break_waiver':
      return action.on_file ? 'Record this meal-break waiver?' : 'Record that no meal-break waiver is on file?'
    case 'work_permit':
      return 'Record this work permit?'
    case 'eligibility_case_decision':
      return action.decision === 'remove' ? 'Remove this employee assignment?' : 'Keep this employee assignment?'
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
  if (type === 'amend_handbook') return <BookOpen size={size} />
  if (type === 'discipline_decision') return <Gavel size={size} />
  if (type === 'ems_promote') return <ArrowUpCircle size={size} />
  if (type === 'inventory_movement' || type === 'inventory_item_create') return <Package size={size} />
  if (type === 'inventory_order_decision') return <Truck size={size} />
  if (type === 'inventory_item_archive') return <Archive size={size} />
  if (type === 'inventory_receipt') return <Receipt size={size} />
  if (type === 'schedule_change' || type === 'schedule_week_draft' || type === 'schedule_note' || type === 'meal_break_waiver' || type === 'work_permit' || type === 'eligibility_case_decision') return <CalendarClock size={size} />
  return <ShieldAlert size={size} />
}
