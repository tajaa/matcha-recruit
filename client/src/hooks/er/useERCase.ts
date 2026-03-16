import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { ERCase } from '../../types/er'

export function useERCase(caseId: string) {
  const [case_, setCase] = useState<ERCase | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetch_ = useCallback(() => {
    setLoading(true)
    setError('')
    api.get<ERCase>(`/er/cases/${caseId}`)
      .then(setCase)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load case'))
      .finally(() => setLoading(false))
  }, [caseId])

  useEffect(() => { fetch_() }, [fetch_])

  const updateCase = useCallback(async (patch: Partial<ERCase>) => {
    const updated = await api.put<ERCase>(`/er/cases/${caseId}`, patch)
    setCase(updated)
  }, [caseId])

  const deleteCase = useCallback(async () => {
    await api.delete(`/er/cases/${caseId}`)
    setCase(null)
  }, [caseId])

  return { case_, loading, error, updateCase, deleteCase, refetch: fetch_ }
}
