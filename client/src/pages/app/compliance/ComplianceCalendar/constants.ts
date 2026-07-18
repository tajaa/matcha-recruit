import type { ComplianceCalendarItem } from '../../../../api/compliance/compliance'

export const STATUS_LABEL: Record<ComplianceCalendarItem['derived_status'], string> = {
  overdue: 'Overdue',
  due_soon: 'Due in 30 days',
  upcoming: 'Due in 90 days',
  future: 'Future',
}

export const STATUS_HINT: Record<ComplianceCalendarItem['derived_status'], string> = {
  overdue: 'Past their deadline. Action needed.',
  due_soon: 'Deadline within 30 days. Schedule action this month.',
  upcoming: 'Deadline 31–90 days out. Plan ahead.',
  future: 'Deadline more than 90 days out. Awareness only.',
}

export const STATUS_VARIANT: Record<
  ComplianceCalendarItem['derived_status'],
  'danger' | 'warning' | 'neutral' | 'success'
> = {
  overdue: 'danger',
  due_soon: 'warning',
  upcoming: 'neutral',
  future: 'success',
}
