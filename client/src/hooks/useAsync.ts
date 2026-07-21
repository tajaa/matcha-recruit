import { useCallback, useEffect, useRef, useState } from 'react'

// The repo's prevailing data-fetch shape, hoisted. 213 files hand-roll the same
// `useState(true)` + fetch-in-`useEffect` + `.finally(() => setLoading(false))`
// triad; this collapses it without introducing React Query or SWR (see the
// house rule in client/CLAUDE.md — adding one is an architectural decision, not
// a per-feature choice).
//
// Two behaviours are deliberate and worth stating, because the hand-rolled
// versions disagreed about both:
//
//   * A reload does NOT clear `data`. The prevailing pattern keeps the old rows
//     on screen and flips only `loading`, so a filter change re-renders in place
//     instead of flashing an empty table.
//   * Out-of-order responses are discarded. Typing in a search box or clicking
//     two filters quickly issues overlapping requests, and the slower one used
//     to win by landing last. Only the newest run may write state.

export type AsyncState<D> = {
  data: D
  loading: boolean
  /** `e.message`, or null when the last run succeeded. */
  error: string | null
  /** Re-run `fn` without clearing `data`. Resolves when the run settles, so a
   *  caller that must not proceed until the list is fresh can await it. */
  reload: () => Promise<void>
  /** Escape hatch for optimistic updates — write `data` without a fetch. */
  setData: (updater: D | ((prev: D) => D)) => void
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

/**
 * Run `fn` on mount and whenever `deps` change.
 *
 * `fn` is held in a ref, so an inline closure over component state is fine and
 * does not need memoising — only `deps` decides when a refetch happens, exactly
 * like the `useEffect` it replaces.
 *
 * `deps` is spread into that effect, so it carries the same rule React applies:
 * its LENGTH must not change between renders. `useAsync(fn, cond ? [a] : [a, b])`
 * throws "the final argument changed size between renders". Pass a fixed-length
 * array and vary the values.
 *
 * For a fetch that should wait on a value, guard inside `fn` rather than
 * branching at the call site:
 *
 *     const { data } = useAsync(() => (id ? getThing(id) : Promise.resolve(null)), [id])
 *
 * Pass `initial` when the caller wants a non-undefined value before the first
 * response — almost always `[]` for a list. It only sets the starting value; a
 * failed run leaves the last-known data in place rather than reverting to it.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T | undefined>
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], initial: T): AsyncState<T>
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
  initial?: T,
): AsyncState<T | undefined> {
  const [data, setData] = useState<T | undefined>(initial)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fnRef = useRef(fn)
  fnRef.current = fn

  // Monotonic id of the newest run. A response whose id is stale is dropped —
  // it belongs to a request a newer one has already superseded.
  const runIdRef = useRef(0)
  const mountedRef = useRef(true)
  // Setting the flag on the way IN is load-bearing, not symmetry. StrictMode
  // dev-mounts every component twice (mount → cleanup → mount), so a cleanup
  // that only ever sets `false` latches the guard off for the component's whole
  // life: every response is then discarded and the page hangs on its loading
  // state. Tests must wrap in <StrictMode> to catch this — renderHook does not
  // apply it by default.
  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const run = useCallback((): Promise<void> => {
    const runId = ++runIdRef.current
    setLoading(true)
    setError(null)
    return fnRef.current()
      .then((result) => {
        if (!mountedRef.current || runId !== runIdRef.current) return
        setData(result)
        setError(null)
      })
      .catch((e) => {
        if (!mountedRef.current || runId !== runIdRef.current) return
        setError(message(e))
      })
      .finally(() => {
        if (!mountedRef.current || runId !== runIdRef.current) return
        setLoading(false)
      })
  }, [])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { run() }, deps)

  return { data, loading, error, reload: run, setData }
}

export type AsyncAction<A extends unknown[], R> = {
  /** Resolves the result, or `undefined` if `fn` threw. */
  run: (...args: A) => Promise<R | undefined>
  busy: boolean
  error: string | null
  reset: () => void
}

/**
 * The mutation counterpart: a one-shot call with its own busy/error state.
 *
 * `run` resolves `undefined` rather than throwing on failure, which preserves
 * the prevailing call-site shape:
 *
 *     const saved = await save.run(form)
 *     if (!saved) return          // error already in save.error
 */
export function useAsyncAction<A extends unknown[], R>(
  fn: (...args: A) => Promise<R>,
): AsyncAction<A, R> {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fnRef = useRef(fn)
  fnRef.current = fn

  const mountedRef = useRef(true)
  // See the note in useAsync: the `true` on mount is what keeps StrictMode's
  // double-mount from latching this guard off permanently.
  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    setBusy(true)
    setError(null)
    try {
      const result = await fnRef.current(...args)
      return result
    } catch (e) {
      // Still report the failure after unmount would be a no-op setState, so
      // guard — but the caller still gets `undefined`, which is what it checks.
      if (mountedRef.current) setError(message(e))
      return undefined
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }, [])

  const reset = useCallback(() => {
    setBusy(false)
    setError(null)
  }, [])

  return { run, busy, error, reset }
}
