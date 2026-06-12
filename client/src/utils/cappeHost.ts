// Cappe/Gummfit dedicated domain — single source of truth for the consumer
// host. VITE_CAPPE_HOST overrides at build time; default is the live domain.
export const CAPPE_HOST = (import.meta.env.VITE_CAPPE_HOST as string | undefined) || 'gummfit.com'

// True when the SPA is being served from the Cappe domain (apex or www) —
// App.tsx mounts the Cappe route tree at "/" there.
export const isCappeHost =
  typeof window !== 'undefined' &&
  (window.location.hostname === CAPPE_HOST || window.location.hostname === `www.${CAPPE_HOST}`)

/** Public hostname a site is served on: custom domain if connected, else
 *  `<subdomain>.<CAPPE_HOST>`. */
export function cappeSiteHost(site: { custom_domain?: string | null; subdomain?: string | null; slug: string }): string {
  return site.custom_domain || `${site.subdomain || site.slug}.${CAPPE_HOST}`
}
