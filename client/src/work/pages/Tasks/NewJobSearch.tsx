import { useCallback, useEffect, useState } from 'react'
import { createJobSearch, getJobSearchSetup, type JobSearchSetup, type JobSearchSummary } from '../../api/matchaWork/jobSearch'
import { errorText } from '../JobSearch/jobSearchLogic'
import NewJobSearchModal from '../JobSearch/NewJobSearchModal'

/** Only mounted while open: consent and allowance don't need search history. */
export default function NewJobSearch({ onCreated, onClose }: {
  onCreated: (search: JobSearchSummary) => void
  onClose: () => void
}) {
  const [setup, setSetup] = useState<JobSearchSetup | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let cancelled = false
    void getJobSearchSetup().then(
      (loaded) => { if (!cancelled) { setSetup(loaded); setError(null) } },
      (e: unknown) => { if (!cancelled) setError(errorText(e, "Couldn't load job search setup.")) },
    )
    return () => { cancelled = true }
  }, [attempt])
  const retry = useCallback(() => setAttempt((n) => n + 1), [])
  return (
    <NewJobSearchModal
      list={setup}
      loadError={error}
      onRetry={retry}
      onCreate={createJobSearch}
      onCreated={onCreated}
      onClose={onClose}
    />
  )
}
