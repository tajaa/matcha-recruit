import { useEffect, useRef } from 'react'
import { setDirtyProbe } from '../../../utils/unsavedGuard'

/** Protect in-progress editor work from being thrown away.
 *
 *  Two halves, because a SPA can lose the work two different ways:
 *  - **In-app navigation** — registers `isDirty` as the module-level probe
 *    `confirmLeave()` reads, so the sidebar / sign-out / back button can ask
 *    before they navigate (see utils/unsavedGuard.ts for why this is not
 *    `useBlocker`: Cappe runs under <BrowserRouter>, not a data router).
 *  - **Leaving the tab** — a `beforeunload` listener, attached only while
 *    dirty so a clean editor never triggers the browser's own prompt.
 *
 *  `isDirty` is read through a ref so a re-created closure never leaves a
 *  stale probe registered. */
export function useUnsavedGuard(isDirty: () => boolean) {
  const probe = useRef(isDirty)
  probe.current = isDirty
  const dirty = isDirty()

  useEffect(() => {
    setDirtyProbe(() => probe.current())
    return () => setDirtyProbe(null)
  }, [])

  useEffect(() => {
    if (!dirty) return
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      // Legacy browsers still need a non-empty returnValue to show the prompt.
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])
}
