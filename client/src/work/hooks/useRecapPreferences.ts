import { useEffect, useState } from 'react'
import { onAuthReset } from '../../api/authReset'
import { useMe } from '../../hooks/useMe'
import { getRecapPreferences } from '../api/matchaWork/recaps'
import { useWorkSurface } from '../routes/WorkSurfaceContext'
import type { RecapPreferences } from '../types'

let cached: { owner: string; promise: Promise<RecapPreferences> } | null = null
onAuthReset(() => { cached = null })
export function rememberRecapPreferences(owner: string, value: RecapPreferences) {
  cached = { owner, promise: Promise.resolve(value) }
}

export function useRecapPreferences(enabled = true) {
  const { me, isPersonal } = useMe()
  const surface = useWorkSurface()
  const [data, setData] = useState<{ owner: string; value: RecapPreferences } | null>(null)
  const owner = me?.user.id
  useEffect(() => {
    let alive = true
    if (owner && isPersonal && surface === 'espresso' && enabled) {
      if (cached?.owner !== owner) cached = { owner, promise: getRecapPreferences() }
      const requested = cached
      void requested.promise.then((value) => { if (alive) setData({ owner, value }) }).catch(() => { if (cached === requested) cached = null })
    }
    return () => { alive = false }
  }, [owner, isPersonal, surface, enabled])
  return data && data.owner === owner && isPersonal && surface === 'espresso' ? data.value : null
}
