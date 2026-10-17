import { useEffect, useSyncExternalStore } from 'react'
import { onAuthReset } from '../../api/authReset'
import { useMe } from '../../hooks/useMe'
import { getRecapPreferences } from '../api/matchaWork/recaps'
import { useWorkSurface } from '../routes/WorkSurfaceContext'
import type { RecapPreferences } from '../types'

let cached: { owner: string; promise: Promise<RecapPreferences>; value?: RecapPreferences } | null = null
const listeners = new Set<() => void>()
const notify = () => { for (const listener of listeners) listener() }
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }
onAuthReset(() => { cached = null; notify() })
export function rememberRecapPreferences(owner: string, value: RecapPreferences) {
  cached = { owner, promise: Promise.resolve(value), value }
  notify()
}

export function useRecapPreferences(enabled = true) {
  const { me, isPersonal } = useMe()
  const surface = useWorkSurface()
  const owner = me?.user.id
  const active = enabled && isPersonal && surface === 'espresso'
  const data = useSyncExternalStore(subscribe, () => active && cached?.owner === owner ? cached?.value ?? null : null, () => null)
  useEffect(() => {
    if (owner && isPersonal && surface === 'espresso' && enabled) {
      if (cached?.owner !== owner) {
        cached = { owner, promise: getRecapPreferences() }
        const requested = cached
        void requested.promise.then((value) => {
          if (cached === requested) { cached = { ...requested, value }; notify() }
        }).catch(() => { if (cached === requested) { cached = null; notify() } })
      }
    }
  }, [owner, isPersonal, surface, enabled])
  return data
}
