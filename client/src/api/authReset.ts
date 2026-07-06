/**
 * Central registry of module-level cache invalidators that must run whenever
 * the authenticated user changes (logout, session-expiry logout). Modules
 * holding a module-scoped cache register here at import time; every logout
 * path calls resetAuthCaches() so no cache survives into the next user's
 * session on the same tab.
 */

const _resetters = new Set<() => void>()

export function onAuthReset(fn: () => void): void {
  _resetters.add(fn)
}

export function resetAuthCaches(): void {
  for (const fn of _resetters) {
    try {
      fn()
    } catch {
      // One bad resetter must not block the others during logout.
    }
  }
}
