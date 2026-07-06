import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

export type IRInfoRequestQuestion = {
  text: string
  source: 'copilot' | 'admin'
}

export type IRInfoRequest = {
  id: string
  recipient_name: string
  recipient_email: string
  questions: IRInfoRequestQuestion[]
  custom_message: string | null
  responses: { question: string; answer: string }[] | null
  status: 'pending' | 'submitted' | 'expired' | 'revoked'
  link: string
  created_at: string | null
  submitted_at: string | null
  expires_at: string | null
}

export function useIRInfoRequests(incidentId: string) {
  const [requests, setRequests] = useState<IRInfoRequest[]>([])
  const [loading, setLoading] = useState(true)

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const refresh = useCallback(() => {
    const id = ++reqId.current
    setLoading(true)
    return api.get<IRInfoRequest[]>(`/ir/incidents/${incidentId}/info-requests`)
      .then((d) => { if (id === reqId.current) setRequests(d) })
      .catch(() => { if (id === reqId.current) setRequests([]) })
      .finally(() => { if (id === reqId.current) setLoading(false) })
  }, [incidentId])

  useEffect(() => { void refresh() }, [refresh])

  const resend = useCallback(async (requestId: string) => {
    const updated = await api.post<IRInfoRequest>(
      `/ir/incidents/${incidentId}/info-requests/${requestId}/resend`, {},
    )
    setRequests((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    return updated
  }, [incidentId])

  const revoke = useCallback(async (requestId: string) => {
    const updated = await api.delete<IRInfoRequest>(
      `/ir/incidents/${incidentId}/info-requests/${requestId}`,
    )
    setRequests((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    return updated
  }, [incidentId])

  return { requests, loading, refresh, resend, revoke }
}
