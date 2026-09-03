import { useCallback, useEffect, useState } from 'react'
import { fetchJobs } from '../../api/employees/employeeSchedule'
import type { ScheduleJob } from '../../types/employeeSchedule'

/** The location's jobs, plus the reload every caller needs.
 *
 *  Both shift-creation surfaces have to offer this list, and a manager who
 *  follows the "add a role first" prompt has to see the new one without a
 *  remount — so the refetch is part of the hook, not something each page
 *  reimplements and then forgets to call. */
export function useScheduleJobs(locationId: string | undefined) {
  const [jobs, setJobs] = useState<ScheduleJob[]>([])

  const reload = useCallback(async () => {
    if (!locationId) {
      setJobs([])
      return
    }
    try {
      const response = await fetchJobs(locationId)
      setJobs(response.jobs)
    } catch {
      setJobs([])
    }
  }, [locationId])

  useEffect(() => { void reload() }, [reload])

  return { jobs, reloadJobs: reload }
}
