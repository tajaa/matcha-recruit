import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { IRIncident } from '../../types/ir'

export function useIRIncident(incidentId: string) {
  const [incident, setIncident] = useState<IRIncident | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const fetch_ = useCallback(() => {
    const id = ++reqId.current
    setLoading(true)
    setError('')
    api.get<IRIncident>(`/ir/incidents/${incidentId}`)
      .then((d) => { if (id === reqId.current) setIncident(d) })
      .catch((e) => { if (id === reqId.current) setError(e instanceof Error ? e.message : 'Failed to load incident') })
      .finally(() => { if (id === reqId.current) setLoading(false) })
  }, [incidentId])

  useEffect(() => { fetch_() }, [fetch_])

  const updateIncident = useCallback(async (patch: Partial<IRIncident>) => {
    const updated = await api.put<IRIncident>(`/ir/incidents/${incidentId}`, patch)
    setIncident(updated)
    return updated
  }, [incidentId])

  const deleteIncident = useCallback(async () => {
    await api.delete(`/ir/incidents/${incidentId}`)
    setIncident(null)
  }, [incidentId])

  return { incident, loading, error, updateIncident, deleteIncident, refetch: fetch_ }
}
