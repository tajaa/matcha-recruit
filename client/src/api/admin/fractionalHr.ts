import { api } from '../client'

// --- Types ---------------------------------------------------------------- //
export type BillingModel = 'monthly_retainer' | 'hours_block' | 'project_fixed' | 'hourly'
export type ClientStatus = 'prospect' | 'active' | 'paused' | 'offboarded'
export type RetainerPeriod = 'weekly' | 'monthly' | 'quarterly'
export type AssignmentRole = 'lead' | 'consultant' | 'jr'
export type ScopeStatus = 'planned' | 'active' | 'on_hold' | 'done'
export type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'review' | 'done'
export type Priority = 'low' | 'medium' | 'high'

export type HoursSummary = {
  billing_model: BillingModel
  retainer_period: RetainerPeriod | null
  total_logged: number
  budget: number | null
  used: number | null
  remaining: number | null
  utilization_pct: number | null
  basis: string | null
  project_fee?: number | null
  billing_rate?: number | null
  billable_amount?: number
}

export type FractionalClient = {
  id: string
  name: string
  company_id: string | null
  company_name?: string | null
  status: ClientStatus
  billing_model: BillingModel
  retainer_hours: number | null
  retainer_period: RetainerPeriod
  rollover_unused: boolean
  billing_rate: number | null
  project_fee: number | null
  currency: string
  industry: string | null
  headcount: number | null
  jurisdictions: string[]
  contact_name: string | null
  contact_email: string | null
  contact_phone: string | null
  lead_pro_id: string | null
  lead_pro_email?: string | null
  start_date: string | null
  notes: string | null
  created_at: string
  updated_at: string
  // list-only enrichments
  hours_summary?: HoursSummary
  open_tasks?: number
  overdue_tasks?: number
}

export type Assignment = { id: string; client_id: string; pro_user_id: string; role: AssignmentRole; email: string }
export type ScopeItem = {
  id: string; client_id: string; service_category: string; title: string; description: string | null
  status: ScopeStatus; priority: Priority; created_at: string; updated_at: string
}
export type Task = {
  id: string; client_id: string; scope_item_id: string | null; title: string; description: string | null
  service_category: string; status: TaskStatus; priority: Priority; assignee_pro_id: string | null
  assignee_email?: string | null; scope_title?: string | null; due_date: string | null
  estimated_hours: number | null; billable: boolean; completed_at: string | null
  created_at: string; updated_at: string
}
export type TimeEntry = {
  id: string; client_id: string; task_id: string | null; pro_id: string; pro_email?: string | null
  task_title?: string | null; hours: number; entry_date: string; note: string | null
  billable: boolean; service_category: string | null; created_at: string
}
export type Pro = { id: string; email: string; role: string }
export type CompanyOption = { id: string; name: string; industry: string | null; status: string }

export type Overview = {
  status_counts: Record<string, number>
  committed_retainer_hours: number | null
  hours_logged_this_month: number | null
  open_tasks: number
  overdue_tasks: number
  tasks_completed_this_month: number
  work_by_category: { service_category: string; count: number }[]
  pro_load: { id: string; email: string; clients_led: number; open_tasks: number; hours_month: number | null }[]
  at_risk: {
    id: string; name: string; status: string; billing_model: string
    retainer_hours: number | null; month_hours: number | null; overdue_tasks: number
  }[]
}

export type ClientDetail = {
  client: FractionalClient
  company: CompanyOption | null
  lead_pro: Pro | null
  assignments: Assignment[]
  hours_summary: HoursSummary
  task_counts: { open_tasks: number; overdue_tasks: number; total_tasks: number }
}

export type Meta = {
  service_categories: string[]
  billing_models: BillingModel[]
  client_statuses: ClientStatus[]
  task_statuses: TaskStatus[]
  scope_statuses: ScopeStatus[]
  priorities: Priority[]
  assignment_roles: AssignmentRole[]
}

const B = '/fractional-hr'

// --- API ------------------------------------------------------------------ //
export const fractionalHr = {
  meta: () => api.get<Meta>(`${B}/meta`),
  pros: () => api.get<{ pros: Pro[] }>(`${B}/pros`),
  linkableCompanies: (q?: string) =>
    api.get<{ companies: CompanyOption[] }>(`${B}/linkable-companies${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  overview: () => api.get<Overview>(`${B}/overview`),

  listClients: (params?: { status?: string; q?: string }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.q) qs.set('q', params.q)
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return api.get<{ clients: FractionalClient[] }>(`${B}/clients${suffix}`)
  },
  createClient: (body: Partial<FractionalClient>) => api.post<FractionalClient>(`${B}/clients`, body),
  getClient: (id: string) => api.get<ClientDetail>(`${B}/clients/${id}`),
  updateClient: (id: string, body: Partial<FractionalClient>) => api.patch<FractionalClient>(`${B}/clients/${id}`, body),
  deleteClient: (id: string) => api.delete<void>(`${B}/clients/${id}`),

  addAssignment: (clientId: string, body: { pro_user_id: string; role: AssignmentRole }) =>
    api.post<Assignment>(`${B}/clients/${clientId}/assignments`, body),
  removeAssignment: (assignmentId: string) => api.delete<void>(`${B}/assignments/${assignmentId}`),

  listScope: (clientId: string) => api.get<{ scope_items: ScopeItem[] }>(`${B}/clients/${clientId}/scope`),
  createScope: (clientId: string, body: Partial<ScopeItem>) => api.post<ScopeItem>(`${B}/clients/${clientId}/scope`, body),
  updateScope: (scopeId: string, body: Partial<ScopeItem>) => api.patch<ScopeItem>(`${B}/scope/${scopeId}`, body),
  deleteScope: (scopeId: string) => api.delete<void>(`${B}/scope/${scopeId}`),

  listTasks: (clientId: string, status?: string) =>
    api.get<{ tasks: Task[] }>(`${B}/clients/${clientId}/tasks${status ? `?status=${status}` : ''}`),
  createTask: (clientId: string, body: Partial<Task>) => api.post<Task>(`${B}/clients/${clientId}/tasks`, body),
  updateTask: (taskId: string, body: Partial<Task>) => api.patch<Task>(`${B}/tasks/${taskId}`, body),
  deleteTask: (taskId: string) => api.delete<void>(`${B}/tasks/${taskId}`),

  listTime: (clientId: string) => api.get<{ time_entries: TimeEntry[] }>(`${B}/clients/${clientId}/time`),
  logTime: (clientId: string, body: Partial<TimeEntry>) => api.post<TimeEntry>(`${B}/clients/${clientId}/time`, body),
  deleteTime: (entryId: string) => api.delete<void>(`${B}/time/${entryId}`),
}

// --- Display helpers ------------------------------------------------------ //
export const SERVICE_LABELS: Record<string, string> = {
  policy: 'Policy development',
  handbook: 'Handbook',
  audit: 'HR audit',
  org_design: 'Org design',
  team_direction: 'HR-team direction',
  coaching: 'Executive coaching',
  strategy: 'HR strategy',
  hiring: 'Hiring',
  compliance: 'Compliance',
  other: 'Other',
}

export const BILLING_LABELS: Record<BillingModel, string> = {
  monthly_retainer: 'Monthly retainer',
  hours_block: 'Hours block',
  project_fixed: 'Fixed project',
  hourly: 'Hourly (T&M)',
}

export const serviceLabel = (key: string) => SERVICE_LABELS[key] ?? key
