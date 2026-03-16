import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { EmployeeDetail } from '../../types/employee'

export function useEmployeeDetail(employeeId: string) {
  const [employee, setEmployee] = useState<EmployeeDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetch_ = useCallback(() => {
    setLoading(true)
    setError('')
    api.get<EmployeeDetail>(`/employees/${employeeId}`)
      .then(setEmployee)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load employee'))
      .finally(() => setLoading(false))
  }, [employeeId])

  useEffect(() => { fetch_() }, [fetch_])

  const updateEmployee = useCallback(async (patch: Partial<EmployeeDetail>) => {
    const updated = await api.put<EmployeeDetail>(`/employees/${employeeId}`, patch)
    setEmployee(updated)
    return updated
  }, [employeeId])

  const updateStatus = useCallback(async (employment_status: string, reason?: string) => {
    const updated = await api.put<EmployeeDetail>(`/employees/${employeeId}/status`, {
      employment_status,
      reason,
    })
    setEmployee(updated)
    return updated
  }, [employeeId])

  const deleteEmployee = useCallback(async () => {
    await api.delete(`/employees/${employeeId}`)
    setEmployee(null)
  }, [employeeId])

  const sendInvite = useCallback(async () => {
    const endpoint = employee?.invitation_status
      ? `/employees/${employeeId}/resend-invite`
      : `/employees/${employeeId}/invite`
    await api.post(endpoint)
    fetch_()
  }, [employeeId, employee?.invitation_status, fetch_])

  return { employee, loading, error, updateEmployee, updateStatus, deleteEmployee, sendInvite, refetch: fetch_ }
}
