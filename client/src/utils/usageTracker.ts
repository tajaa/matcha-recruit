/**
 * First-party usage tracking — page views for every surface, logged in or not.
 *
 * No third-party service, no fingerprinting, no cross-site anything: an
 * anonymous visitor id in localStorage plus the bearer token when one exists.
 * Events queue in memory and flush in batches, so navigation never waits on a
 * network round trip.
 *
 * Modeled on errorReporter.ts — raw fetch (not api.request), silent failures.
 * Analytics is droppable; it must never surface an error or block the user.
 */

import { API_BASE } from '../api/client'
import { getAccessToken } from '../api/authStorage'
import { normalizeSensitivePath } from './urlSecurity'

type Surface = 'web' | 'public' | 'werk_desktop'

type UsageEvent = {
  event: 'page_view' | 'session_start' | 'heartbeat'
  path: string
  surface: Surface
  ts: string
}

const FLUSH_INTERVAL_MS = 10_000
const QUEUE_MAX = 50
const DEDUP_WINDOW_MS = 1000

const VISITOR_KEY = 'matcha_vid'

let _queue: UsageEvent[] = []
let _lastPath: string | null = null
let _lastPathAt = 0
let _installed = false

/** Authenticated product surfaces. Everything else (marketing, auth funnel,
 *  public token pages) counts as `public` — that split is the whole point of
 *  tracking logged-out traffic separately. */
const APP_PREFIXES = ['/app', '/admin', '/work', '/werk', '/werk-lite', '/ops', '/broker', '/portal']

function getVisitorId(): string | undefined {
  try {
    let id = localStorage.getItem(VISITOR_KEY)
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem(VISITOR_KEY, id)
    }
    return id
  } catch {
    return undefined // storage blocked (private mode / embedded webview)
  }
}

/**
 * Collapse identifying segments before anything leaves the browser.
 *
 * Public routes carry live secrets in the URL (`/report/<token>`, `/s/<token>`,
 * `/hb/<token>`) — those must never reach the analytics store. The server
 * re-normalizes too (it can't trust us), but scrubbing here means the token
 * never crosses the wire in the first place.
 */
export function normalizePath(pathname: string): string {
  return normalizeSensitivePath(pathname)
}

function surfaceFor(path: string): Surface {
  return APP_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`)) ? 'web' : 'public'
}

function enqueue(ev: UsageEvent) {
  _queue.push(ev)
  if (_queue.length > QUEUE_MAX) _queue = _queue.slice(-QUEUE_MAX)
}

export function trackPageView(path: string) {
  const normalized = normalizePath(path)
  const now = Date.now()
  // React StrictMode double-invokes effects in dev; a real user also can't
  // meaningfully view the same page twice in a second.
  if (_lastPath === normalized && now - _lastPathAt < DEDUP_WINDOW_MS) return
  _lastPath = normalized
  _lastPathAt = now

  enqueue({
    event: 'page_view',
    path: normalized,
    surface: surfaceFor(normalized),
    ts: new Date().toISOString(),
  })
}

function flush(useKeepalive = false) {
  if (_queue.length === 0) return
  const events = _queue
  _queue = []

  try {
    // Deliberate raw read (documented exception): flush() must stay sync for
    // the pagehide beacon, and a dead session must not trigger
    // ensureFreshToken's logout redirect.
    const token = getAccessToken()
    void fetch(`${API_BASE}/usage/beacon`, {
      method: 'POST',
      // keepalive lets the request outlive the page on tab close. sendBeacon
      // can't be used: it cannot set an Authorization header, and we'd lose
      // user attribution on the last page view of every session.
      keepalive: useKeepalive,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ visitor_id: getVisitorId(), events }),
    }).catch(() => {
      /* drop — analytics is best-effort */
    })
  } catch {
    /* drop */
  }
}

export function installUsageTracker() {
  if (_installed) return
  _installed = true

  setInterval(() => flush(), FLUSH_INTERVAL_MS)

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush(true)
  })
  window.addEventListener('pagehide', () => flush(true))
}
