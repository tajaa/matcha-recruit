// Stale-chunk recovery shared between the Vite `vite:preloadError` listener
// (main.tsx) and the React ErrorBoundary. After a deploy, hashed chunks from
// the previous build 404 (or get SPA-fallback HTML) for tabs still running the
// old index. Reloading once picks up the fresh manifest.
//
// vite:preloadError only fires for Vite's __vitePreload helper. A React.lazy()
// import that fails surfaces instead as a thrown error caught by the
// ErrorBoundary — so both call sites need the same detection + one-shot guard.

const RELOAD_KEY = 'matcha_chunk_reload_at'
const RELOAD_WINDOW_MS = 60_000

// Messages browsers use when a dynamic import / module script fails to load.
const CHUNK_ERROR_PATTERNS = [
  'failed to fetch dynamically imported module',
  'error loading dynamically imported module',
  'valid javascript mime type', // 'text/html' is not a valid JavaScript MIME type
  'importing a module script failed', // Safari
  'unable to preload css',
]

export function isStaleChunkError(error: unknown): boolean {
  if (!error) return false
  if (typeof error === 'object' && (error as { name?: string }).name === 'ChunkLoadError') return true
  const msg = (error instanceof Error ? error.message : String(error)).toLowerCase()
  return CHUNK_ERROR_PATTERNS.some((p) => msg.includes(p))
}

// Reload at most once per RELOAD_WINDOW_MS so a genuinely broken/missing asset
// surfaces normally instead of looping reloads. Returns true if a reload was
// triggered (caller should stop further handling).
export function reloadForStaleChunk(): boolean {
  const last = Number(sessionStorage.getItem(RELOAD_KEY) ?? 0)
  if (Date.now() - last < RELOAD_WINDOW_MS) return false
  sessionStorage.setItem(RELOAD_KEY, String(Date.now()))
  window.location.reload()
  return true
}
