import { useCallback, useSyncExternalStore } from 'react'

/**
 * Subscribe to a CSS media query in JS.
 *
 * Use this instead of Tailwind's `hidden md:flex` when the two branches must
 * not BOTH be mounted. The kanban board is the cautionary case: rendering the
 * mobile pager and the desktop board together mounted two `KanbanColumn`s per
 * lane sharing one `menuRef`, so the later-rendered (invisible) copy won the
 * ref and the visible column's "+" menu closed itself on mousedown before its
 * buttons could fire. CSS-hiding a subtree hides pixels, not state.
 *
 * Where `matchMedia` is missing (jsdom), every query reads false.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback((onChange: () => void) => {
    const mql = window.matchMedia?.(query)
    if (!mql) return () => {}
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])
  return useSyncExternalStore(subscribe, () => window.matchMedia?.(query).matches ?? false, () => false)
}

/** Tailwind's `md` breakpoint — the boundary the board uses to swap between the
 *  five-lane drag board and the one-column touch pager. */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 768px)')
}
