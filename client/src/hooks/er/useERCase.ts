import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { ERCase } from '../../types/er'

export function useERCase(caseId: string) {
  const [case_, setCase] = useState<ERCase | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const fetch_ = useCallback(() => {
    const id = ++reqId.current
    setLoading(true)
    setError('')
    api.get<ERCase>(`/er/cases/${caseId}`)
      .then((d) => { if (id === reqId.current) setCase(d) })
      .catch((e) => { if (id === reqId.current) setError(e instanceof Error ? e.message : 'Failed to load case') })
      .finally(() => { if (id === reqId.current) setLoading(false) })
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
