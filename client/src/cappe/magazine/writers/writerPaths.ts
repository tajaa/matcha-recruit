/** Gummfit Magazines URLs for writer accounts (a writer's account is one
 *  magazine-only site; see server/app/cappe/services/magazine/writers.py). */
export const writerPaths = {
  landing: '/cappe/magazines/start',
  signup: '/cappe/magazines/signup',
  login: '/cappe/magazines/login',
  /** Sends a writer to their magazine's stories, or to onboarding without one. */
  home: '/cappe/writer',
  onboarding: '/cappe/writer/new',
} as const

export const storiesPath = (siteId: string) => `/cappe/sites/${siteId}/stories`
