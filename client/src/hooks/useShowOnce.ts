import { useEffect, useState } from 'react'

/**
 * Boolean state that starts `true` the very first time this key has been
 * seen on this browser, then `false` forever after (localStorage-flagged) —
 * plus a setter so a "?" button can retrigger it manually any time.
 *
 * Used to auto-show a "How it works" modal once per feature on first visit
 * without needing a backend flag — browser-scoped is enough for onboarding
 * UX (not a tenant-security concern), so no schema change is needed.
 */
export function useShowOnce(key: string): [boolean, (v: boolean) => void] {
  const storageKey = `matcha:seen-how-it-works:${key}`
  const [show, setShow] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem(storageKey)) {
      setShow(true)
      localStorage.setItem(storageKey, '1')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return [show, setShow]
}
