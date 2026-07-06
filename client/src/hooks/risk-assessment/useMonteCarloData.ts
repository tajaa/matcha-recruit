import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../../api/client'
import type { MonteCarloResult } from '../../types/risk-assessment'

export function useMonteCarloData(qs: string) {
  const [data, setData] = useState<MonteCarloResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reqId = useRef(0)

  const load = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<MonteCarloResult>(`/risk-assessment/monte-carlo${qs}`)
      if (id !== reqId.current) return
      setData(result)
    } catch {
      if (id !== reqId.current) return
      setError('No Monte Carlo simulation available')
      setData(null)
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [qs])

  useEffect(() => { load() }, [load])
  useEffect(() => () => { reqId.current++ }, [])

  return { data, loading, error, reload: load }
}
