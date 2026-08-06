// returnTo must be an app-relative path ('/i/abc'), never absolute — blocks open redirects.
const KEY = 'tellus_return_to'

export function sanitizeReturnTo(v: string | null): string | null {
  if (!v || !v.startsWith('/') || v.startsWith('//') || v.startsWith('/\\')) return null
  // Reject a scheme-looking prefix (e.g. '/javascript:alert(1)') without
  // banning ordinary paths/queries that merely contain a colon later on.
  if (/^\/[a-z][a-z0-9+.-]*:/i.test(v)) return null
  return v
}

export function stashReturnTo(v: string | null) {
  const s = sanitizeReturnTo(v)
  if (s) sessionStorage.setItem(KEY, s)
}

export function popReturnTo(): string | null {
  const v = sessionStorage.getItem(KEY)
  sessionStorage.removeItem(KEY)
  return sanitizeReturnTo(v)
}

export function clearReturnTo() {
  sessionStorage.removeItem(KEY)
}
