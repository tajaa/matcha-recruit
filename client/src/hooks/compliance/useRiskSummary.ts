import { useCallback, useEffect, useState } from 'react'
import { fetchRiskSummary } from '../../api/compliance'
import type { ComplianceRiskSummary } from '../../types/compliance'

export function useRiskSummary() {
  const [data, setData] = useState<ComplianceRiskSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const refetch = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      setData(await fetchRiskSummary())
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  return { data, loading, error, refetch }
}
