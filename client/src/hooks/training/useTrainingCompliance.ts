import { useCallback, useEffect, useState } from 'react'
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

  const refetch = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [c, o, r] = await Promise.all([
        trainingApi.compliance(),
        trainingApi.overdue(),
        trainingApi.listRequirements(),
      ])
      setCompliance(c)
      setOverdue(o)
      setRequirements(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load training data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refetch()
  }, [refetch])

  return { compliance, overdue, requirements, loading, error, refetch }
}
