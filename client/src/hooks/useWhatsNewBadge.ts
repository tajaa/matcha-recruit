import { useCallback, useEffect, useState } from 'react'
import { useMe } from './useMe'
import {
  markTenantUpdatesSeen,
  unseenTenantUpdatesCount,
} from '../data/tenantUpdates'

// Unseen count for the sidebar "What's New" entry. Purely local: the feed is
// a static data file, so seen-state is a per-user localStorage id set — no
// server round-trip (unlike useSidebarBadges).
export function useWhatsNewBadge() {
  const { me } = useMe()
  const userId = me?.user?.id
  const source = me?.profile?.signup_source
  const [count, setCount] = useState(0)

  useEffect(() => {
    setCount(userId ? unseenTenantUpdatesCount(userId, source) : 0)
  }, [userId, source])

  const markSeen = useCallback(() => {
    if (!userId) return
    markTenantUpdatesSeen(userId, source)
    setCount(0)
  }, [userId, source])

  return { count, markSeen }
}
