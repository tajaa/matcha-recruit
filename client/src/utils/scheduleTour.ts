const SESSION_KEY = 'matcha.schedule.tour-auto-opened'

/** Whether a first-visit schedule tour should open by itself.
 *
 *  The schedule page and the shift editor each have one, and a new manager
 *  reaches both within a minute of each other — two unprompted slide decks in
 *  a row, before they have made a single shift. So only one tour auto-opens
 *  per browser session; the other waits behind its Help button until a later
 *  visit. `seenKey` is the tour's own "dismissed for good" localStorage key.
 */
export function shouldAutoOpenScheduleTour(seenKey: string): boolean {
  try {
    if (window.localStorage.getItem(seenKey) === 'seen') return false
    const opened = window.sessionStorage.getItem(SESSION_KEY)
    // Same key again is this tour re-asking (a remount), not a second tour.
    if (opened && opened !== seenKey) return false
    window.sessionStorage.setItem(SESSION_KEY, seenKey)
    return true
  } catch {
    return true
  }
}
