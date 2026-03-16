import type { BadgeVariant } from '../components/ui'

export type EmploymentStatus =
  | 'active'
  | 'on_leave'
  | 'suspended'
  | 'on_notice'
  | 'furloughed'
  | 'terminated'
  | 'offboarded'

export type EmploymentType = 'full_time' | 'part_time' | 'contractor'

export type PayClassification = 'exempt' | 'hourly'

export type OnboardingTaskStatus = 'pending' | 'completed' | 'skipped'

export type OnboardingCategory =
  | 'documents'
  | 'equipment'
  | 'training'
  | 'admin'
  | 'return_to_work'

export type Employee = {
  id: string
  email: string
  work_email: string | null
  personal_email: string | null
  first_name: string
  last_name: string
  work_state: string | null
  employment_type: string | null
  start_date: string | null
  termination_date: string | null
  manager_id: string | null
  manager_name: string | null
  user_id: string | null
  invitation_status: string | null
  pay_classification: string | null
  pay_rate: number | null
  work_city: string | null
  job_title: string | null
  department: string | null
  employment_status: string | null
  status_changed_at: string | null
  status_reason: string | null
  created_at: string
}

export type EmployeeDetail = Employee & {
  phone: string | null
  address: string | null
  emergency_contact: Record<string, string> | null
  updated_at: string
}

export type OnboardingTask = {
  id: string
  employee_id: string
  task_id: string | null
  leave_request_id: string | null
  title: string
  description: string | null
  category: string
  is_employee_task: boolean
  due_date: string | null
  status: string
  completed_at: string | null
  completed_by: string | null
  notes: string | null
  created_at: string
}

export type OnboardingProgress = {
  total: number
  completed: number
  pending: number
  has_onboarding: boolean
}

export type BulkUploadResponse = {
  total_rows: number
  created: number
  failed: number
  errors: { row: number; error: string }[]
  employee_ids: string[]
  credentials_created: number
}

export const statusLabel: Record<string, string> = {
  active: 'Active',
  on_leave: 'On Leave',
  suspended: 'Suspended',
  on_notice: 'On Notice',
  furloughed: 'Furloughed',
  terminated: 'Terminated',
  offboarded: 'Offboarded',
}

export const typeLabel: Record<string, string> = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  contractor: 'Contractor',
}

export const TYPE_OPTIONS = Object.entries(typeLabel).map(([value, label]) => ({ value, label }))

export const statusVariant: Record<string, BadgeVariant> = {
  active: 'success',
  on_leave: 'warning',
  suspended: 'danger',
  on_notice: 'warning',
  furloughed: 'warning',
  terminated: 'danger',
  offboarded: 'danger',
}
