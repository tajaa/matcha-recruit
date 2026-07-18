import { api } from '../client'

export type TrainingRequirement = {
  id: string
  company_id: string
  title: string
  description: string | null
  training_type: string
  jurisdiction: string | null
  frequency_months: number | null
  applies_to: 'all' | 'supervisor' | 'nonsupervisor'
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export type TrainingRecord = {
  id: string
  company_id: string
  employee_id: string
  requirement_id: string | null
  title: string
  training_type: string
  status: 'assigned' | 'in_progress' | 'completed' | 'expired' | 'waived'
  assigned_date: string | null
  due_date: string | null
  completed_date: string | null
  expiration_date: string | null
  provider: string | null
  certificate_number: string | null
  score: number | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export type TrainingComplianceRow = {
  requirement_id: string
  title: string
  training_type: string
  jurisdiction: string | null
  frequency_months: number | null
  total_assigned: number
  completed: number
  overdue: number
}

export type TrainingOverdueRow = {
  record_id: string
  training_title: string
  training_type: string
  due_date: string | null
  assigned_date: string | null
  status: string
  employee_id: string
  first_name: string
  last_name: string
  email: string
}

export type MyTrainingRecord = TrainingRecord & {
  required_minutes: number | null
  has_lesson: boolean
  started_at: string | null
  attested_at: string | null
}

export type LessonResponse = {
  record_id: string
  template_id: string
  template_key: string
  variant: 'supervisor' | 'nonsupervisor'
  title: string
  summary_for_certificate: string | null
  required_minutes: number
  pass_score_percent: number
  sections: Array<{
    id: string
    title: string
    estimated_minutes?: number
    body_md: string
    key_takeaways?: string[]
  }>
  quiz: {
    questions: Array<{
      id: string
      prompt: string
      options: Array<{ key: string; text: string }>
    }>
  }
  started_at: string | null
  status: string
}

export type QuizResult = {
  record_id: string
  attempt_number: number
  score_percent: number
  correct: number
  total: number
  passed: boolean
  pass_score_percent: number
}

export type AttestResult = {
  record_id: string
  status: 'completed'
  completed_date: string
  expiration_date: string
  score_percent: number
  certificate_id: string
}

// HR-side
export const trainingApi = {
  listRequirements: () => api.get<TrainingRequirement[]>('/training/requirements'),
  getRequirement: (id: string) => api.get<TrainingRequirement>(`/training/requirements/${id}`),
  getRecord: (id: string) => api.get<TrainingRecord>(`/training/records/${id}`),
  bulkAssign: (requirement_id: string) =>
    api.post<{ assigned_count: number; requirement_id: string; message?: string }>(
      '/training/records/bulk-assign',
      { requirement_id },
    ),
  listRecords: (params: { employee_id?: string; status?: string; overdue?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (params.employee_id) q.set('employee_id', params.employee_id)
    if (params.status) q.set('status', params.status)
    if (params.overdue !== undefined) q.set('overdue', String(params.overdue))
    const qs = q.toString()
    return api.get<TrainingRecord[]>(`/training/records${qs ? `?${qs}` : ''}`)
  },
  compliance: () => api.get<TrainingComplianceRow[]>('/training/compliance'),
  overdue: () => api.get<TrainingOverdueRow[]>('/training/overdue'),
  certificateUrl: (record_id: string) =>
    api.get<{ url: string }>(`/training/records/${record_id}/certificate-url`),
}

// Employee-side
export const employeeTrainingApi = {
  myRecords: () => api.get<MyTrainingRecord[]>('/training/records/me'),
  lesson: (record_id: string) => api.get<LessonResponse>(`/training/records/${record_id}/lesson`),
  start: (record_id: string) =>
    api.post<{ started_at: string; status: string; already_started: boolean }>(
      `/training/records/${record_id}/start`,
    ),
  submitQuiz: (record_id: string, answers: Record<string, string>, elapsed_seconds?: number) =>
    api.post<QuizResult>(`/training/records/${record_id}/quiz`, { answers, elapsed_seconds }),
  attest: (record_id: string, attestation_text?: string) =>
    api.post<AttestResult>(`/training/records/${record_id}/attest`, attestation_text ? { attestation_text } : {}),
  myCertificateUrl: (record_id: string) =>
    api.get<{ url: string }>(`/training/records/me/${record_id}/certificate-url`),
}
