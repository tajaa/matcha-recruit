import { useCallback, useEffect, useRef, useState } from 'react'
import {
  trainingApi,
  type TrainingComplianceRow,
  type TrainingOverdueRow,
  type TrainingRequirement,
} from '../../api/training'

export function useTrainingCompliance() {
  const [compliance, setCompliance] = useState<TrainingComplianceRow[]>([])
  const [overdue, setOverdue] = useState<TrainingOverdueRow[]>([])
  const [requirements, setRequirements] = useState<TrainingRequirement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  const refetch = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    setError(null)
    try {
      const [c, o, r] = await Promise.all([
        trainingApi.compliance(),
        trainingApi.overdue(),
        trainingApi.listRequirements(),
      ])
      if (id !== reqId.current) return
      setCompliance(c)
      setOverdue(o)
      setRequirements(r)
    } catch (e) {
      if (id !== reqId.current) return
      setError(e instanceof Error ? e.message : 'Failed to load training data')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refetch()
  }, [refetch])

  return { compliance, overdue, requirements, loading, error, refetch }
}
