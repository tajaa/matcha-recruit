/**
 * Guarded full-page redirect for URLs that come back from our API (Stripe checkout
 * URLs, OAuth authorize URLs). Defense-in-depth: these URLs originate from our own
 * authenticated backend today, but assigning `window.location.href` straight from a
 * response is an open-redirect primitive if a response is ever attacker-influenced.
 * `externalRedirect` navigates only when the target is same-origin or an allow-listed
 * https host, and refuses everything else (including `javascript:` / `data:` and http
 * downgrades).
 */

// https hosts we deliberately hand off to. Matches the host exactly or as a subdomain.
const ALLOWED_HOSTS: RegExp[] = [
  /(^|\.)stripe\.com$/, // checkout.stripe.com, billing.stripe.com, …
  /(^|\.)accounts\.google\.com$/, // Google Workspace OAuth
  /(^|\.)slack\.com$/, // Slack OAuth
  /(^|\.)tryfinch\.com$/, // Finch Connect (HRIS)
  /(^|\.)gusto\.com$/, // Gusto OAuth
]

/** True when `url` is safe to navigate to: same-origin, or an allow-listed https host. */
export function isAllowedRedirect(url: string): boolean {
  let u: URL
  try {
    u = new URL(url, window.location.origin)
  } catch {
    return false
  }
  if (u.origin === window.location.origin) return true
  if (u.protocol !== 'https:') return false // blocks javascript:, data:, http downgrade
  return ALLOWED_HOSTS.some((re) => re.test(u.hostname))
}

/**
 * Navigate the page to `url` iff it passes {@link isAllowedRedirect}. Returns whether
 * the navigation was allowed; a blocked URL is logged and no navigation occurs.
 */
export function externalRedirect(url: string): boolean {
  if (!isAllowedRedirect(url)) {
    console.error('[externalRedirect] blocked navigation to disallowed URL:', url)
    return false
  }
  window.location.href = url
  return true
}
