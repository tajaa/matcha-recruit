import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { OnboardingTask } from '../../types/employee'

export function useOnboardingTasks(employeeId: string) {
  const [tasks, setTasks] = useState<OnboardingTask[]>([])
  const [loading, setLoading] = useState(true)

  const fetch_ = useCallback(() => {
    setLoading(true)
    api.get<OnboardingTask[]>(`/employees/${employeeId}/onboarding`)
      .then(setTasks)
      .catch(() => setTasks([]))
      .finally(() => setLoading(false))
  }, [employeeId])

  useEffect(() => { fetch_() }, [fetch_])

  const updateTask = useCallback(async (taskId: string, patch: { status?: string; notes?: string }) => {
    const updated = await api.patch<OnboardingTask>(`/employees/${employeeId}/onboarding/${taskId}`, patch)
    setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)))
    return updated
  }, [employeeId])

  const deleteTask = useCallback(async (taskId: string) => {
    await api.delete(`/employees/${employeeId}/onboarding/${taskId}`)
    setTasks((prev) => prev.filter((t) => t.id !== taskId))
  }, [employeeId])

  return { tasks, loading, updateTask, deleteTask, refetch: fetch_ }
}
