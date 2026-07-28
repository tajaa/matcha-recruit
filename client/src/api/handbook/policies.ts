import { api } from '../client'
import type { PolicyResponse } from '../../types/policy'

export const policies = {
  list: (status?: string, category?: string): Promise<PolicyResponse[]> => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (category) params.set('category', category)
    const qs = params.toString()
    return api.get<PolicyResponse[]>(`/policies${qs ? `?${qs}` : ''}`)
  },
  get: (id: string) => api.get<PolicyResponse>(`/policies/${id}`),
  create: (data: FormData) => api.upload<PolicyResponse>('/policies', data),
  update: (id: string, data: Record<string, unknown>) => api.put<PolicyResponse>(`/policies/${id}`, data),
  delete: (id: string) => api.delete<void>(`/policies/${id}`),
}
