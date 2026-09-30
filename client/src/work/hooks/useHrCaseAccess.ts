import { useEffect, useState } from 'react'
import { getHrCaseAccess } from '../api/hrCases'

// Whether the signed-in user can open the HR Cases page. One request per
// page load per user (the sidebar mounts often); the server re-checks on
// every HR-cases route regardless.
const cache = new Map<string, Promise<boolean>>()

export function useHrCaseAccess(userId: string | undefined, enabled: boolean): boolean {
  const [state, setState] = useState<{ key: string; allowed: boolean } | null>(null)
  const key = enabled && userId ? userId : null

  useEffect(() => {
    if (!key) return
    let alive = true
    let pending = cache.get(key)
    if (!pending) {
      const request = getHrCaseAccess().then(
        (r) => r.hr_access,
        () => {
          // A failed check isn't an answer: forget it so the next mount asks
          // again, instead of hiding HR Cases until a full reload.
          if (cache.get(key) === request) cache.delete(key)
          return false
        },
      )
      pending = request
      cache.set(key, pending)
    }
    void pending.then((allowed) => { if (alive) setState({ key, allowed }) })
    return () => { alive = false }
  }, [key])

  return key !== null && state?.key === key && state.allowed
}

/** Test seam: forget cached answers. */
export function resetHrCaseAccessCache() {
  cache.clear()
}
