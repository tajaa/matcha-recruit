import { getAccessToken, LAST_ACTIVITY_KEY } from './authStorage'
import { logoutSession } from './client'

const configuredIdleMinutes = Number(import.meta.env.VITE_SESSION_IDLE_MINUTES ?? 30)
const IDLE_MS = (Number.isFinite(configuredIdleMinutes) && configuredIdleMinutes > 0
  ? configuredIdleMinutes
  : 30) * 60 * 1000
const ACTIVITY_WRITE_INTERVAL_MS = 30 * 1000

function tokenIssuedAt(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof payload.iat === 'number' ? payload.iat * 1000 : null
  } catch {
    return null
  }
}

function readLastActivity(token: string): number {
  try {
    const stored = Number(localStorage.getItem(LAST_ACTIVITY_KEY))
    if (Number.isFinite(stored) && stored > 0) return stored
  } catch { /* storage may be blocked */ }
  return tokenIssuedAt(token) ?? Date.now()
}

/** Install user-activity locking for a tab that may stay open for days. */
export function installSessionSecurity(): () => void {
  let lastWrite = 0
  let loggingOut = false

  const noteActivity = () => {
    if (!getAccessToken()) return
    const now = Date.now()
    if (now - lastWrite < ACTIVITY_WRITE_INTERVAL_MS) return
    lastWrite = now
    try { localStorage.setItem(LAST_ACTIVITY_KEY, String(now)) } catch { /* storage may be blocked */ }
  }

  const checkIdle = () => {
    const token = getAccessToken()
    if (!token || loggingOut) return
    if (Date.now() - readLastActivity(token) >= IDLE_MS) {
      loggingOut = true
      void logoutSession()
    }
  }

  const activityEvents: (keyof WindowEventMap)[] = ['pointerdown', 'keydown', 'touchstart', 'scroll']
  for (const event of activityEvents) window.addEventListener(event, noteActivity, { passive: true })
  document.addEventListener('visibilitychange', checkIdle)
  window.addEventListener('focus', checkIdle)
  const timer = window.setInterval(checkIdle, 30_000)
  checkIdle()

  return () => {
    for (const event of activityEvents) window.removeEventListener(event, noteActivity)
    document.removeEventListener('visibilitychange', checkIdle)
    window.removeEventListener('focus', checkIdle)
    window.clearInterval(timer)
  }
}
