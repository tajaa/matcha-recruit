import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type {
  CorrectiveAction,
  CorrectiveActionCreate,
  CorrectiveActionListResponse,
} from '../../types/ir'

/**
 * Structured corrective actions (CAPA) for one incident.
 *
 * Mirrors the request-race guard in useIRIncident: a stale in-flight fetch
 * that resolves after a newer one is discarded. Unlike the older IR panels,
 * mutations surface their error to the caller (no silent `catch {}`) so the
 * panel can show inline "couldn't save — retry".
 */
export function useCorrectiveActions(incidentId: string) {
  const [actions, setActions] = useState<CorrectiveAction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const refetch = useCallback(() => {
    const id = ++reqId.current
    setLoading(true)
    setError('')
    api.get<CorrectiveActionListResponse>(`/ir/incidents/${incidentId}/corrective-actions`)
      .then((d) => { if (id === reqId.current) setActions(d.actions) })
      .catch((e) => { if (id === reqId.current) setError(e instanceof Error ? e.message : 'Failed to load corrective actions') })
      .finally(() => { if (id === reqId.current) setLoading(false) })
  }, [incidentId])

  useEffect(() => { refetch() }, [refetch])

  const createAction = useCallback(async (payload: CorrectiveActionCreate) => {
    const created = await api.post<CorrectiveAction>(`/ir/incidents/${incidentId}/corrective-actions`, payload)
    setActions((prev) => [...prev, created])
    return created
  }, [incidentId])

  const updateAction = useCallback(async (actionId: string, patch: Partial<CorrectiveAction>) => {
    const updated = await api.put<CorrectiveAction>(`/ir/incidents/corrective-actions/${actionId}`, patch)
    setActions((prev) => prev.map((a) => (a.id === actionId ? updated : a)))
    return updated
  }, [])

  const deleteAction = useCallback(async (actionId: string) => {
    await api.delete(`/ir/incidents/corrective-actions/${actionId}`)
    setActions((prev) => prev.filter((a) => a.id !== actionId))
  }, [])

  return { actions, loading, error, refetch, createAction, updateAction, deleteAction }
}
