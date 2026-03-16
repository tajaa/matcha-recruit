import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { IRIncident } from '../../types/ir'

export function useIRIncident(incidentId: string) {
  const [incident, setIncident] = useState<IRIncident | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetch_ = useCallback(() => {
    setLoading(true)
    setError('')
    api.get<IRIncident>(`/ir/incidents/${incidentId}`)
      .then(setIncident)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load incident'))
      .finally(() => setLoading(false))
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
