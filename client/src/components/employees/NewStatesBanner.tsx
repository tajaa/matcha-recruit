import { useState, useEffect } from 'react'
import { AlertTriangle } from 'lucide-react'
import { api } from '../../api/client'

type NewStates = {
  employee_states: string[]
  location_states: string[]
  new_jurisdictions: string[]
}

/** Warns when the company has active employees in states where it has no
 *  business location — jurisdictions with compliance obligations it may never
 *  have set up. Renders nothing when there are none. */
export function NewStatesBanner() {
  const [data, setData] = useState<NewStates | null>(null)

  useEffect(() => {
    let live = true
    api.get<NewStates>('/onboarding/new-states')
      .then((d) => { if (live) setData(d) })
      .catch(() => { if (live) setData(null) })
    return () => { live = false }
  }, [])

  if (!data || data.new_jurisdictions.length === 0) return null

  return (
    <div className="rounded-lg border border-amber-500/25 bg-amber-500/[0.06] px-4 py-3 flex items-start gap-3">
      <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
      <div className="text-sm text-amber-100/90">
        You have employees in{' '}
        <span className="font-medium">{data.new_jurisdictions.join(', ')}</span>{' '}
        but no business location there. Set up compliance for{' '}
        {data.new_jurisdictions.length === 1 ? 'this jurisdiction' : 'these jurisdictions'} to
        surface their new-hire notices and requirements.
      </div>
    </div>
  )
}
