import { useEffect, useState, useCallback } from 'react'
import { api } from '../../api/client'
import type { MonteCarloResult } from '../../types/risk-assessment'

export function useMonteCarloData(qs: string) {
  const [data, setData] = useState<MonteCarloResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<MonteCarloResult>(`/risk-assessment/monte-carlo${qs}`)
      setData(result)
    } catch {
      setError('No Monte Carlo simulation available')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [qs])

  useEffect(() => { load() }, [load])

  return { data, loading, error, reload: load }
}
