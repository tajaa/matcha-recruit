import { cappeApi } from '../../api'
import type { CappeReaderSubscription } from '../../types'
import { readerMagazinePath } from './readerPaths'

export const day = (iso: string | null) =>
  (iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '')

/** "Renews Nov 21, 2026", "Ends Nov 21, 2026" or "Card failing", as a reader reads it. */
export function subscriptionState(sub: CappeReaderSubscription): string {
  if (sub.cancel_at_period_end) return sub.current_period_end ? `Ends ${day(sub.current_period_end)}` : 'Ending'
  if (sub.status === 'past_due') return 'Card failing: update it on the magazine’s account page'
  return sub.current_period_end ? `Renews ${day(sub.current_period_end)}` : 'Active'
}

/** Free months from the writer: until when, or for good. */
export const compState = (comp: { expires_at: string | null }) =>
  (comp.expires_at ? `Free until ${day(comp.expires_at)}` : 'Free, from the writer')

/** Open Stripe Checkout for a magazine; it comes back to the magazine's page here. */
export async function startCheckout(slug: string): Promise<void> {
  const page = `${window.location.origin}${readerMagazinePath(slug)}`
  const res = await cappeApi.post<{ checkout_url: string }>(`/reader/magazines/${encodeURIComponent(slug)}/subscribe`, {
    success_url: `${page}?subscribed=1`,
    cancel_url: page,
  })
  window.location.assign(res.checkout_url)
}

/** Stop at the end of the paid month (`cancel`), or keep it going. */
export const changeSubscription = (id: string, cancel: boolean) =>
  cappeApi.post<{ status: string; cancel_at_period_end: boolean }>(
    `/reader/subscriptions/${encodeURIComponent(id)}/${cancel ? 'cancel' : 'resume'}`)
