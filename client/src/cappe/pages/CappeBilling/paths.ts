// Billing page addresses, in their own module so the sidebar, the auth pages
// and the editor can link to billing without importing the page itself.
export const BILLING_PATH = '/cappe/billing'

/** Billing page that immediately starts checkout for `plan` (see CappeBilling). */
export function billingStartPath(plan: string, interval?: string | null): string {
  const params = new URLSearchParams({ start: plan, interval: interval === 'year' ? 'year' : 'month' })
  return `${BILLING_PATH}?${params.toString()}`
}
