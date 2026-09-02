/** Session-scoped storage for Matcha bearer tokens.
 *
 * localStorage survives browser restarts and made an unattended workstation a
 * month-long session. sessionStorage survives a reload but is destroyed with
 * the tab/window. The refresh token therefore no longer rests in persistent
 * origin storage, while the short-lived access token keeps existing API and
 * WebSocket flows reload-safe.
 *
 * Every storage access here is best-effort: Safari with site data blocked, some
 * embedded webviews, and private-mode quirks make `sessionStorage` *throw*
 * rather than return null. In that case tokens live in module memory for the
 * lifetime of the page — strictly narrower than sessionStorage, so the security
 * posture only improves — instead of the write escaping into a caller's
 * `catch` and being reported as a login failure.
 */

const ACCESS_KEY = 'matcha_access_token'
const REFRESH_KEY = 'matcha_refresh_token'
export const LAST_ACTIVITY_KEY = 'matcha_last_activity_at'

// Fallback for contexts where Web Storage throws (see the module docstring).
let memoryAccess: string | null = null
let memoryRefresh: string | null = null
// Mirrors LAST_ACTIVITY_KEY. localStorage is the cross-tab channel; this is the
// authority when it is unavailable, and the reason a sibling tab's logout can
// no longer leave this tab with a broken idle clock.
let memoryLastActivity = 0

function purgeLegacyPersistentTokens(): void {
  try {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
    const legacyOutboxKeys: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key === 'channels_outbox_v1' || key?.startsWith('channels_outbox_v1:')) legacyOutboxKeys.push(key)
    }
    for (const key of legacyOutboxKeys) localStorage.removeItem(key)
  } catch { /* storage may be blocked */ }
}

purgeLegacyPersistentTokens()

export function getAccessToken(): string | null {
  try { return sessionStorage.getItem(ACCESS_KEY) ?? memoryAccess } catch { return memoryAccess }
}

export function getRefreshToken(): string | null {
  try { return sessionStorage.getItem(REFRESH_KEY) ?? memoryRefresh } catch { return memoryRefresh }
}

export function setAuthTokens(
  accessToken: string,
  refreshToken: string,
  options: { recordActivity?: boolean } = {},
): void {
  purgeLegacyPersistentTokens()
  memoryAccess = accessToken
  memoryRefresh = refreshToken
  try {
    sessionStorage.setItem(ACCESS_KEY, accessToken)
    sessionStorage.setItem(REFRESH_KEY, refreshToken)
  } catch { /* storage blocked — the in-memory copies above carry the session */ }
  if (options.recordActivity !== false) recordActivity()
}

export function clearAuthTokens(): void {
  purgeLegacyPersistentTokens()
  memoryAccess = null
  memoryRefresh = null
  memoryLastActivity = 0
  try {
    sessionStorage.removeItem(ACCESS_KEY)
    sessionStorage.removeItem(REFRESH_KEY)
  } catch { /* storage may be blocked */ }
  try { localStorage.removeItem(LAST_ACTIVITY_KEY) } catch { /* storage may be blocked */ }
}

/** Stamp "the user did something just now", for the idle lock. */
export function recordActivity(at: number = Date.now()): void {
  memoryLastActivity = at
  try { localStorage.setItem(LAST_ACTIVITY_KEY, String(at)) } catch { /* storage may be blocked */ }
}

/** Newest activity stamp known to this tab, or 0 when there is none.
 *
 * Deliberately NOT falling back to the access token's `iat`: the token is
 * re-minted on every refresh, so that fallback slid forward on its own and
 * silently disabled the idle lock wherever localStorage was unavailable.
 */
export function readLastActivity(): number {
  let stored = 0
  try {
    const raw = Number(localStorage.getItem(LAST_ACTIVITY_KEY))
    if (Number.isFinite(raw) && raw > 0) stored = raw
  } catch { /* storage may be blocked */ }
  return Math.max(stored, memoryLastActivity)
}
