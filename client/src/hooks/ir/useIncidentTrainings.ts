import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

export type IncidentTraining = {
  id: string
  employee_id: string
  employee_name: string
  title: string
  status: string
  due_date: string | null
  completed_date: string | null
  source_note: string | null
}

export type AssignTrainingResult = {
  assigned_count: number
  accelerated_count: number
  already_open_count: number
  requirement_id: string
}

/** Training records an incident triggered (source_type='incident') — mirrors useCorrectiveActions. */
export function useIncidentTrainings(incidentId: string) {
  const [trainings, setTrainings] = useState<IncidentTraining[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const refetch = useCallback(() => {
    const id = ++reqId.current
    setLoading(true)
    setError('')
    api.get<IncidentTraining[]>(`/ir/incidents/${incidentId}/trainings`)
      .then((d) => { if (id === reqId.current) setTrainings(d) })
      .catch((e) => { if (id === reqId.current) setError(e instanceof Error ? e.message : 'Failed to load trainings') })
      .finally(() => { if (id === reqId.current) setLoading(false) })
  }, [incidentId])

  useEffect(() => { refetch() }, [refetch])

  const assignTraining = useCallback(async (body: {
    requirement_id: string
    employee_ids?: string[]
    due_date?: string | null
    note?: string | null
    corrective_action_id?: string | null
  }) => {
    const result = await api.post<AssignTrainingResult>(`/ir/incidents/${incidentId}/assign-training`, body)
    refetch()
    return result
  }, [incidentId, refetch])

  return { trainings, loading, error, refetch, assignTraining }
}
