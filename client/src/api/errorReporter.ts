/**
 * Native client-side error reporter — captures uncaught JS errors, unhandled
 * promise rejections, React render errors, and failed API responses, and POSTs
 * them to /api/client-errors so they land in the backend logs + DB. No paid
 * SaaS, no third-party JS.
 *
 * Install once at app boot via `installErrorReporter()`.
 */

const BASE = import.meta.env.VITE_API_URL ?? '/api'

interface ClientErrorPayload {
  kind: 'js_error' | 'promise_rejection' | 'api_error' | 'react_error'
  message: string
  stack?: string
  url?: string
  api_endpoint?: string
  api_status_code?: number
  context?: Record<string, unknown>
}

// Dedup window — same fingerprint won't be sent more than once per 30s
const _recentFingerprints = new Map<string, number>()
const DEDUP_WINDOW_MS = 30_000

function _fingerprint(p: ClientErrorPayload): string {
  return `${p.kind}|${p.message.slice(0, 200)}|${p.api_endpoint || ''}|${p.api_status_code || ''}`
}

// Query strings can carry secrets (/auth/beta?token=…, reset ?token=, SSO
// ?code=) — report the path only, never the query or fragment.
function _redactUrl(raw: string): string {
  try {
    const u = new URL(raw, window.location.origin)
    return `${u.origin}${u.pathname}`
  } catch {
    return raw.split(/[?#]/)[0]
  }
}

// JWTs and anything token-shaped must not be persisted to the error store.
const JWT_RE = /eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g

function _scrub(value: unknown, maxLen = 500): string | undefined {
  if (value == null) return undefined
  let s: string
  try {
    s = typeof value === 'string' ? value : JSON.stringify(value)
  } catch {
    return undefined
  }
  return s.replace(JWT_RE, '[redacted-jwt]').slice(0, maxLen)
}

let _inFlight = 0

async function _send(payload: ClientErrorPayload): Promise<void> {
  // Hard cap concurrent in-flight reports to avoid feedback loops
  if (_inFlight > 5) return
  _inFlight++
  try {
    const fp = _fingerprint(payload)
    const now = Date.now()
    const last = _recentFingerprints.get(fp)
    if (last && now - last < DEDUP_WINDOW_MS) return
    _recentFingerprints.set(fp, now)

    // Trim the map periodically so it doesn't grow unbounded
    if (_recentFingerprints.size > 200) {
      const cutoff = now - DEDUP_WINDOW_MS
      for (const [k, t] of _recentFingerprints) {
        if (t < cutoff) _recentFingerprints.delete(k)
      }
    }

    const token = localStorage.getItem('matcha_access_token')
    // Use raw fetch — must NOT go through api.request or we infinite loop on
    // any reporter-generated error.
    await fetch(`${BASE}/client-errors`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        ...payload,
        message: _scrub(payload.message) ?? '',
        stack: payload.stack ? _scrub(payload.stack, 4000) : undefined,
        url: _redactUrl(payload.url ?? window.location.href),
        // Endpoints can carry path-embedded share tokens (/s/:token,
        // /report/:token) or a query string — drop the query/fragment and
        // scrub before the endpoint lands in the error store.
        api_endpoint: payload.api_endpoint
          ? _scrub(payload.api_endpoint.split(/[?#]/)[0])
          : undefined,
        context: payload.context
          ? Object.fromEntries(
              Object.entries(payload.context).map(([k, v]) => [
                k,
                typeof v === 'number' || typeof v === 'boolean' ? v : _scrub(v),
              ]),
            )
          : undefined,
      }),
      // No-await on response — fire and forget
      keepalive: true,
    }).catch(() => {
      // Silent — reporter must never throw or it'll crash the global handler
    })
  } catch {
    // swallow
  } finally {
    _inFlight--
  }
}

export function reportJsError(error: Error | unknown, context?: Record<string, unknown>): void {
  const err = error instanceof Error ? error : new Error(String(error))
  void _send({
    kind: 'js_error',
    message: err.message || 'Unknown error',
    stack: err.stack,
    context,
  })
}

export function reportPromiseRejection(reason: unknown): void {
  const message =
    reason instanceof Error
      ? reason.message
      : typeof reason === 'string'
        ? reason
        : JSON.stringify(reason).slice(0, 500)
  const stack = reason instanceof Error ? reason.stack : undefined
  void _send({
    kind: 'promise_rejection',
    message: message || 'Unhandled promise rejection',
    stack,
  })
}

export function reportApiError(opts: {
  endpoint: string
  status: number
  message: string
  body?: unknown
}): void {
  void _send({
    kind: 'api_error',
    message: opts.message || `${opts.status} ${opts.endpoint}`,
    api_endpoint: opts.endpoint,
    api_status_code: opts.status,
    context: opts.body ? { body: _scrub(opts.body) } : undefined,
  })
}

export function reportReactError(error: Error, componentStack?: string): void {
  void _send({
    kind: 'react_error',
    message: error.message || 'React render error',
    stack: error.stack,
    context: componentStack ? { component_stack: componentStack } : undefined,
  })
}

export function installErrorReporter(): void {
  // Uncaught synchronous errors
  window.addEventListener('error', (event) => {
    if (event.error) {
      reportJsError(event.error, {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      })
    } else {
      void _send({
        kind: 'js_error',
        message: event.message || 'Unknown window error',
        context: { filename: event.filename, lineno: event.lineno, colno: event.colno },
      })
    }
  })

  // Unhandled promise rejections
  window.addEventListener('unhandledrejection', (event) => {
    reportPromiseRejection(event.reason)
  })
}
