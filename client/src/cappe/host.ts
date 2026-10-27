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

/** On the Gummfit domain the Cappe tree is served at "/", so the /gummfit and
 *  /cappe prefixes only clutter public URLs (gummfit.com/gummfit/login). Off the
 *  Gummfit host (hey-matcha.com) the prefix is what routes the request, so it
 *  stays. /gummfit/admin is the Matcha-staff console and is never rewritten. */
export function cappePath(path: string, onCappeHost: boolean = isCappeHost): string {
  if (!onCappeHost || /^\/gummfit\/admin(?:[/?#]|$)/i.test(path)) return path
  const m = path.match(/^\/(?:gummfit|cappe)(?=[/?#]|$)(.*)$/i)
  if (!m) return path
  return m[1].startsWith('/') ? m[1] : `/${m[1]}`
}

/** Sign-in entry points, written once so every page links the same URL. */
export const cappeAuthPaths = {
  login: cappePath('/cappe/login'),
  signup: cappePath('/gummfit/website-setup'),
  forgotPassword: cappePath('/cappe/forgot-password'),
} as const
