const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const TOKENISH_RE = /^(?=.*\d)[A-Za-z0-9_-]{20,}$/
const ROOT_SECRET_ROUTES = new Set([
  's', 'hb', 'candidate-interview', 'report', 'offer', 'invite', 'intake',
  'request-info', 'sign', 'sign-document', 'join-channel',
])

/** Remove identifying and bearer-token path segments before telemetry leaves the browser. */
export function normalizeSensitivePath(pathname: string): string {
  const clean = (pathname || '/').split('?')[0].split('#')[0]
  const segments = clean.split('/')
  return (
    segments
      .map((segment, index) => {
        if (!segment) return segment
        const first = segments[1]
        if (index === 2 && ROOT_SECRET_ROUTES.has(first) && !(first === 'intake' && segment === 'external')) {
          return ':token'
        }
        if (index === 3 && ((first === 'intake' && segments[2] === 'external') || (first === 'register' && segments[2] === 'invite'))) {
          return ':token'
        }
        if (UUID_RE.test(segment)) return ':id'
        if (/^\d+$/.test(segment)) return ':id'
        if (TOKENISH_RE.test(segment)) return ':token'
        return segment
      })
      .join('/') || '/'
  ).slice(0, 300)
}

/** Return a same-origin relative navigation target, or null when unsafe. */
export function safeSameOriginPath(raw: string | null | undefined): string | null {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return null
  if (raw.includes('\\') || [...raw].some((char) => {
    const code = char.charCodeAt(0)
    return code <= 0x1f || code === 0x7f
  })) return null
  try {
    const parsed = new URL(raw, window.location.origin)
    if (parsed.origin !== window.location.origin) return null
    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    return null
  }
}
