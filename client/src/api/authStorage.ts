/** Session-scoped storage for Matcha bearer tokens.
 *
 * localStorage survives browser restarts and made an unattended workstation a
 * month-long session. sessionStorage survives a reload but is destroyed with
 * the tab/window. The refresh token therefore no longer rests in persistent
 * origin storage, while the short-lived access token keeps existing API and
 * WebSocket flows reload-safe.
 */

const ACCESS_KEY = 'matcha_access_token'
const REFRESH_KEY = 'matcha_refresh_token'
export const LAST_ACTIVITY_KEY = 'matcha_last_activity_at'

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
  try { return sessionStorage.getItem(ACCESS_KEY) } catch { return null }
}

export function getRefreshToken(): string | null {
  try { return sessionStorage.getItem(REFRESH_KEY) } catch { return null }
}

export function setAuthTokens(
  accessToken: string,
  refreshToken: string,
  options: { recordActivity?: boolean } = {},
): void {
  purgeLegacyPersistentTokens()
  sessionStorage.setItem(ACCESS_KEY, accessToken)
  sessionStorage.setItem(REFRESH_KEY, refreshToken)
  if (options.recordActivity !== false) {
    try { localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now())) } catch { /* storage may be blocked */ }
  }
}

export function clearAuthTokens(): void {
  purgeLegacyPersistentTokens()
  try {
    sessionStorage.removeItem(ACCESS_KEY)
    sessionStorage.removeItem(REFRESH_KEY)
  } catch { /* storage may be blocked */ }
  try { localStorage.removeItem(LAST_ACTIVITY_KEY) } catch { /* storage may be blocked */ }
}
