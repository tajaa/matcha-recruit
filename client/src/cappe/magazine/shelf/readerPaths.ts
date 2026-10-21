/** Gummfit reader accounts: people who subscribe to magazines and sell
 *  nothing. Their dashboard lists every magazine they hold
 *  (server/app/cappe/routes/reader.py). */
export const readerPaths = {
  signup: '/cappe/reader/signup',
  login: '/cappe/reader/login',
  home: '/cappe/reader',
} as const

export const readerMagazinePath = (slug: string) => `/cappe/reader/m/${encodeURIComponent(slug)}`

export const readerStoryPath = (slug: string, story: string) =>
  `${readerMagazinePath(slug)}/${encodeURIComponent(story)}`

/** Where to go after signing in: `next` only when it is the reader's own
 *  dashboard (a magazine's paywall links straight to one of its pages). */
export function readerNext(next: string | null): string {
  return next && /^\/cappe\/reader(?:[/?]|$)/.test(next) ? next : readerPaths.home
}

const SLUG = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/

/** A magazine's handle from what a reader types: `salt`, `salt.gummfit.com`,
 *  or a link to one of its pages. Null when it can't be one. */
export function magazineSlugFrom(input: string): string | null {
  const text = input.trim().toLowerCase()
  if (!text) return null
  if (SLUG.test(text)) return text
  let url: URL
  try {
    url = new URL(/^[a-z]+:\/\//.test(text) ? text : `https://${text}`)
  } catch {
    return null
  }
  const onDashboard = url.pathname.match(/\/reader\/m\/([^/?#]+)/)
  if (onDashboard) return SLUG.test(onDashboard[1]) ? onDashboard[1] : null
  const label = url.hostname.split('.')[0]
  return SLUG.test(label) ? label : null
}
