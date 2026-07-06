import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { OnboardingTask } from '../../types/employee'

export function useOnboardingTasks(employeeId: string) {
  const [tasks, setTasks] = useState<OnboardingTask[]>([])
  const [loading, setLoading] = useState(true)

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const fetch_ = useCallback(() => {
    const id = ++reqId.current
    setLoading(true)
    api.get<OnboardingTask[]>(`/employees/${employeeId}/onboarding`)
      .then((d) => { if (id === reqId.current) setTasks(d) })
      .catch(() => { if (id === reqId.current) setTasks([]) })
      .finally(() => { if (id === reqId.current) setLoading(false) })
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
