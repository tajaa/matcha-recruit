import { getAccessToken } from './client';

export const LEAVE_TYPES = [
  'fmla',
  'state_pfml',
  'parental',
  'bereavement',
  'jury_duty',
  'medical',
  'military',
  'unpaid_loa',
] as const;

export const NOTICE_TYPES = [
  'fmla_eligibility_notice',
  'fmla_designation_notice',
  'state_leave_notice',
  'return_to_work_notice',
] as const;

export type LeaveType = typeof LEAVE_TYPES[number];
export type LeaveStatus = 'requested' | 'approved' | 'denied' | 'active' | 'completed' | 'cancelled';

export interface LeaveRequest {
  id: string;
  employee_id: string;
  org_id: string;
  leave_type: LeaveType;
  reason: string | null;
  start_date: string;
  end_date: string | null;
  expected_return_date: string | null;
  actual_return_date: string | null;
  status: LeaveStatus;
  intermittent: boolean;
  intermittent_schedule: string | null;
  hours_approved: number | null;
  hours_used: number | null;
  denial_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveRequestAdmin extends LeaveRequest {
  employee_name: string | null;
}

export interface LeaveDeadline {
  id: string;
  leave_request_id: string;
  org_id: string;
  deadline_type: string;
  due_date: string;
  status: 'pending' | 'completed' | 'overdue' | 'waived';
  escalation_level: number;
  completed_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveNoticeDocument {
  id: string;
  org_id: string;
  employee_id: string;
  doc_type: string;
  title: string;
  description: string | null;
  storage_path: string | null;
  status: string;
  expires_at: string | null;
  signed_at: string | null;
  assigned_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveRequestCreate {
  leave_type: LeaveType;
  start_date: string;
  end_date?: string;
  expected_return_date?: string;
  reason?: string;
  intermittent?: boolean;
  intermittent_schedule?: string;
}

export interface LeaveActionRequest {
  action: 'approve' | 'deny' | 'activate' | 'complete' | 'extend';
  denial_reason?: string;
  end_date?: string;
  expected_return_date?: string;
  actual_return_date?: string;
  hours_approved?: number;
  notes?: string;
}

export interface PlaceOnLeavePayload {
  leave_type: LeaveType;
  start_date: string;
  end_date?: string;
  expected_return_date?: string;
  reason?: string;
  notes?: string;
}

export interface ReturnCheckinPayload {
  returning: boolean;
  action?: 'extend' | 'new_leave';
  new_end_date?: string;
  new_expected_return_date?: string;
  new_leave_type?: LeaveType;
  new_start_date?: string;
  notes?: string;
}

interface LeaveListResponse {
  requests: LeaveRequest[];
  total: number;
}

async function requestWithAuth<T>(url: string, options: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

export const leaveApi = {
  listAdminRequests: (params?: { status?: string; leave_type?: string }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set('status', params.status);
    if (params?.leave_type) search.set('leave_type', params.leave_type);
    const query = search.toString() ? `?${search.toString()}` : '';
    return requestWithAuth<LeaveRequestAdmin[]>(`/api/employees/leave/requests${query}`);
  },

  getAdminRequest: (leaveId: string) =>
    requestWithAuth<LeaveRequestAdmin>(`/api/employees/leave/requests/${leaveId}`),

  updateAdminRequest: (leaveId: string, payload: LeaveActionRequest) =>
    requestWithAuth<{ message: string; status: string }>(`/api/employees/leave/requests/${leaveId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  getEligibility: (leaveId: string) =>
    requestWithAuth<Record<string, unknown>>(`/api/employees/leave/requests/${leaveId}/eligibility`),

  listDeadlines: (leaveId: string) =>
    requestWithAuth<LeaveDeadline[]>(`/api/employees/leave/requests/${leaveId}/deadlines`),

  updateDeadline: (leaveId: string, deadlineId: string, payload: { action: 'complete' | 'waive'; notes?: string }) =>
    requestWithAuth<LeaveDeadline>(`/api/employees/leave/requests/${leaveId}/deadlines/${deadlineId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  createNotice: (leaveId: string, notice_type: typeof NOTICE_TYPES[number]) =>
    requestWithAuth<LeaveNoticeDocument>(`/api/employees/leave/requests/${leaveId}/notices`, {
      method: 'POST',
      body: JSON.stringify({ notice_type }),
    }),

  assignReturnToWorkTasks: (employeeId: string, leaveId: string) =>
    requestWithAuth<Record<string, unknown>[]>(`/api/employees/${employeeId}/onboarding/assign-rtw/${leaveId}`, {
      method: 'POST',
    }),

  getEmployeeEligibility: (employeeId: string) =>
    requestWithAuth<Record<string, unknown>>(`/api/employees/${employeeId}/leave/eligibility`),

  getEmployeeLeaveHistory: (employeeId: string, status?: string) => {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return requestWithAuth<LeaveRequestAdmin[]>(`/api/employees/leave/employees/${employeeId}/requests${query}`);
  },

  placeOnLeave: (employeeId: string, payload: PlaceOnLeavePayload) =>
    requestWithAuth<{ leave_id: string; employment_status: string }>(`/api/employees/${employeeId}/leave/place`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  returnCheckin: (leaveId: string, payload: ReturnCheckinPayload) =>
    requestWithAuth<Record<string, unknown>>(`/api/employees/leave/requests/${leaveId}/return-checkin`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  extendLeave: (leaveId: string, payload: { end_date: string; expected_return_date?: string; notes?: string }) =>
    requestWithAuth<{ message: string; status: string }>(`/api/employees/leave/requests/${leaveId}`, {
      method: 'PATCH',
      body: JSON.stringify({ action: 'extend', ...payload }),
    }),

  getMyRequests: (status?: string) => {
    const query = status ? `?status_filter=${encodeURIComponent(status)}` : '';
    return requestWithAuth<LeaveListResponse>(`/api/v1/portal/me/leave${query}`);
  },

  getMyRequest: (leaveId: string) =>
    requestWithAuth<LeaveRequest>(`/api/v1/portal/me/leave/${leaveId}`),

  submitMyRequest: (payload: LeaveRequestCreate) =>
    requestWithAuth<LeaveRequest>('/api/v1/portal/me/leave/request', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  cancelMyRequest: (leaveId: string) =>
    requestWithAuth<{ status: string; leave_id: string }>(`/api/v1/portal/me/leave/${leaveId}`, {
      method: 'DELETE',
    }),

  getMyEligibility: () =>
    requestWithAuth<Record<string, unknown>>('/api/v1/portal/me/leave/eligibility'),
};
