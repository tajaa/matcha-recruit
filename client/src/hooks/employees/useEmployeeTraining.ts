import { useCallback, useEffect, useState } from 'react'
import { trainingApi, type TrainingRecord } from '../../api/training/training'

/** Training records for one employee's detail page — mirrors useCredentialManager's shape. */
export function useEmployeeTraining(employeeId: string) {
  const [records, setRecords] = useState<TrainingRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(() => {
    setLoading(true)
    setError('')
    trainingApi.listRecords({ employee_id: employeeId })
      .then(setRecords)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load training records'))
      .finally(() => setLoading(false))
  }, [employeeId])

  useEffect(() => { refetch() }, [refetch])

  const waive = useCallback(async (recordId: string, reason: string) => {
    const updated = await trainingApi.waiveRecord(recordId, reason)
    setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)))
    return updated
  }, [])

  const certificateUrl = useCallback((recordId: string) => trainingApi.certificateUrl(recordId), [])

  return { records, loading, error, refetch, waive, certificateUrl }
}
