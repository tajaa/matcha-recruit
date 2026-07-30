import { useEffect, useState } from 'react'
import { listEvents } from '../api/events'

const POLL_MS = 60_000

/** Polls the logged-events total for the sidebar Events badge. `enabled`
 *  gates the fetch entirely (no request without the `ems` flag + review
 *  permission — backend would 403). Single owner of the cadence + the
 *  limit:1 count-only query; WorkSidebar (via useSidebarData) and
 *  WerkLiteSidebar both consume it — previously each sidebar carried its
 *  own byte-for-byte-identical copy of this effect. */
export function useLoggedEventsCount(enabled: boolean): number {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!enabled) return
    const load = () => {
      listEvents({ status: 'logged', limit: 1 }).then((r) => setCount(r.total)).catch(() => {})
    }
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [enabled])

  return count
}

/** Badge text for the logged-events count. `compact` is for the
 *  collapsed-rail chip, which only has room for one glyph ('!'); expanded
 *  sidebar rows show '9+'. */
export function formatEventsBadge(count: number, compact = false): string {
  if (count > 9) return compact ? '!' : '9+'
  return String(count)
}
