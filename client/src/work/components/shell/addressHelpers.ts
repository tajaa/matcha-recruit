import { useEffect } from 'react'
import type { PostalAddress } from '../../types'

export const EMPTY_ADDRESS: PostalAddress = {
  name: '', line1: '', line2: '', city: '', region: '', postal_code: '', country: 'US', phone: '',
}

/** One line, the way the confirmation card shows it. */
export function addressLine(a: PostalAddress): string {
  const locality = [a.region, a.postal_code].filter(Boolean).join(' ')
  return [a.name, a.line1, a.line2, a.city, locality, a.country].filter(Boolean).join(', ')
}

/** Scroll a settings section into view when the URL points at it
 *  (Espresso's "Add a payment card" button links to /settings#payment-cards). */
export function useScrollToHash(id: string, ready: boolean) {
  useEffect(() => {
    if (!ready || typeof window === 'undefined' || window.location.hash !== `#${id}`) return
    document.getElementById(id)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }, [id, ready])
}
