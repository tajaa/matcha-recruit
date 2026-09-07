import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchPlanningInputs } from '../../api/employees/employeeSchedule'
import type { PlanningInputs } from '../../types/employeeSchedule'

/** What a scheduler should SEE before deciding who works: each person's load
 *  this week, availability, time away, caps, the open seats, the house
 *  policy, whether the state's law is on file. Last-request-wins: `reload`
 *  is also called after every applied write, so two reads can be in flight
 *  against different scopes at once and the slower one must not paint. */
export function usePlanningInputs(locationId: string, weekStart: string) {
  const [inputs, setInputs] = useState<PlanningInputs | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestToken = useRef(0)

  const reload = useCallback(() => {
    const token = ++requestToken.current
    if (!locationId) {
      setInputs(null)
      setLoading(false)
      setError(null)
      return
    }
    setLoading(true)
    void fetchPlanningInputs(locationId, weekStart)
      .then((result) => {
        if (token !== requestToken.current) return
        setInputs(result)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (token !== requestToken.current) return
        setError(cause instanceof Error ? cause.message : 'Could not load the planning inputs.')
      })
      .finally(() => { if (token === requestToken.current) setLoading(false) })
  }, [locationId, weekStart])

  // Fetch on mount and whenever the scope changes — the same shape as every
  // sibling hook here (useScheduleJobs, useEmployees, useOnboardingTasks). The
  // synchronous setState the rule objects to is the spinner going up before
  // the request leaves.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { reload() }, [reload])

  return { inputs, loading, error, reload }
}
