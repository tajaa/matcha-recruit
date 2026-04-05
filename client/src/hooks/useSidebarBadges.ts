import { useEffect, useRef, useCallback, useState } from 'react'
import { useMe } from './useMe'
import { ensureFreshToken } from '../api/client'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// Sections that use localStorage-based since timestamps
type TimestampSection = 'ir' | 'er' | 'escalations'
// All badge sections
export type BadgeSection = TimestampSection | 'inbox' | 'notifications'

export type SidebarBadges = Record<BadgeSection, number>

const EMPTY: SidebarBadges = { ir: 0, er: 0, escalations: 0, inbox: 0, notifications: 0 }
const POLL_MS = 60_000
// Sections where the badge is purely server-tracked (not localStorage-based).
// Calling markSeen on these only clears the local optimistic state — the server
// count won't drop until the user actually reads the items in-app.
const SERVER_TRACKED: BadgeSection[] = ['inbox', 'notifications']

function storageKey(userId: string, section: TimestampSection): string {
  return `sidebar_seen_${userId}_${section}`
}

function getSince(userId: string, section: TimestampSection): string | null {
  return localStorage.getItem(storageKey(userId, section))
}

function setSince(userId: string, section: TimestampSection, iso: string) {
  localStorage.setItem(storageKey(userId, section), iso)
}

export function useSidebarBadges() {
  const { me } = useMe()
  const userId = me?.user?.id
  const [badges, setBadges] = useState<SidebarBadges>(EMPTY)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchBadges = useCallback(async () => {
    if (!userId) return

    const params = new URLSearchParams()
    const sinceIr = getSince(userId, 'ir')
    const sinceEr = getSince(userId, 'er')
    const sinceEsc = getSince(userId, 'escalations')
    if (sinceIr) params.set('since_ir', sinceIr)
    if (sinceEr) params.set('since_er', sinceEr)
    if (sinceEsc) params.set('since_escalations', sinceEsc)

    try {
      const token = await ensureFreshToken()
      if (!token) return
      const res = await fetch(`${BASE}/dashboard/sidebar-badges?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setBadges({
          ir: data.ir ?? 0,
          er: data.er ?? 0,
          escalations: data.escalations ?? 0,
          inbox: data.inbox ?? 0,
          notifications: data.notifications ?? 0,
        })
      }
    } catch {
      // non-fatal
    }
  }, [userId])

  useEffect(() => {
    if (!userId) return
    fetchBadges()
    timerRef.current = setInterval(fetchBadges, POLL_MS)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [userId, fetchBadges])

  const markSeen = useCallback((section: BadgeSection) => {
    if (!userId) return
    if (!SERVER_TRACKED.includes(section)) {
      // localStorage-tracked: set the since timestamp so future polls
      // only count items created after this visit
      const now = new Date().toISOString()
      setSince(userId, section as TimestampSection, now)
      // Optimistically clear the badge locally
      setBadges((prev) => ({ ...prev, [section]: 0 }))
    }
    // For server-tracked sections (inbox, notifications), don't touch local
    // state — the badge reflects real DB state and will only drop when the
    // user actually reads the items. Just refetch to get fresh count.
    setTimeout(fetchBadges, 300)
  }, [userId, fetchBadges])

  return { badges, markSeen, refetch: fetchBadges }
}
