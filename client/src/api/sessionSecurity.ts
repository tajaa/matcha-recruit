import { getAccessToken, readLastActivity, recordActivity } from './authStorage'
import { ensureFreshToken, logoutSession } from './client'

const configuredIdleMinutes = Number(import.meta.env.VITE_SESSION_IDLE_MINUTES ?? 30)
const IDLE_MS = (Number.isFinite(configuredIdleMinutes) && configuredIdleMinutes > 0
  ? configuredIdleMinutes
  : 30) * 60 * 1000
const ACTIVITY_WRITE_INTERVAL_MS = 30 * 1000
const TICK_MS = 30 * 1000

/** Install user-activity locking for a tab that may stay open for days. */
export function installSessionSecurity(): () => void {
  let lastWrite = 0
  let loggingOut = false
  let refreshing = false

  const noteActivity = () => {
    if (!getAccessToken()) return
    const now = Date.now()
    if (now - lastWrite < ACTIVITY_WRITE_INTERVAL_MS) return
    lastWrite = now
    recordActivity(now)
  }

  /* The server's idle clock is `now - refresh_token.iat > 30m`, and `iat` only
   * advances when /auth/refresh is actually called. Left to the 401-retry path
   * alone that clock tracks REQUEST traffic, not the user: someone scrolling
   * and typing in an editor that issues no API call for 30 minutes stays alive
   * here and silently ages out there, then loses unsaved work to a hard 401 on
   * their next save. Ticking ensureFreshToken() while the user is demonstrably
   * active keeps both clocks measuring the same thing. It is nearly free —
   * ensureFreshToken only calls the network inside the last 60s of the access
   * token's life. */
  const keepSessionWarm = async () => {
    if (refreshing || loggingOut) return
    if (!getAccessToken()) return
    if (Date.now() - readLastActivity() >= IDLE_MS) return
    refreshing = true
    try { await ensureFreshToken() } catch { /* transport blip — retry next tick */ }
    finally { refreshing = false }
  }

  const checkIdle = () => {
    const token = getAccessToken()
    if (!token || loggingOut) return
    // No stamp at all means this tab never saw activity and never recorded a
    // login — treat it as idle rather than immortal.
    if (Date.now() - readLastActivity() >= IDLE_MS) {
      loggingOut = true
      void logoutSession()
    }
  }

  const tick = () => {
    checkIdle()
    void keepSessionWarm()
  }

  /* A reload restores this tab's session from sessionStorage, but the shared
   * activity marker may be gone — cleared, blocked, or removed by a sibling
   * tab's logout. Loading the page IS activity, so seed the stamp. Without
   * this the checkIdle() below reads a zero stamp and signs a live session
   * straight out. (The old code got this for free by falling back to the
   * token's `iat`, which is also why its idle lock never fired.) */
  if (getAccessToken() && readLastActivity() === 0) recordActivity()

  const activityEvents: (keyof WindowEventMap)[] = ['pointerdown', 'keydown', 'touchstart', 'scroll']
  for (const event of activityEvents) window.addEventListener(event, noteActivity, { passive: true })
  document.addEventListener('visibilitychange', checkIdle)
  window.addEventListener('focus', checkIdle)
  const timer = window.setInterval(tick, TICK_MS)
  checkIdle()

  return () => {
    for (const event of activityEvents) window.removeEventListener(event, noteActivity)
    document.removeEventListener('visibilitychange', checkIdle)
    window.removeEventListener('focus', checkIdle)
    window.clearInterval(timer)
  }
}
