import { cappePath } from '../../host'

/** Gummfit Magazines URLs for writer accounts (a writer's account is one
 *  magazine-only site; see server/app/cappe/services/magazine/writers.py). */
export const writerPaths = {
  landing: cappePath('/cappe/magazines/start'),
  signup: cappePath('/cappe/magazines/signup'),
  login: cappePath('/cappe/magazines/login'),
  /** Sends a writer to their magazine's stories, or to onboarding without one. */
  home: '/cappe/writer',
  onboarding: '/cappe/writer/new',
} as const

export const storiesPath = (siteId: string) => `/cappe/sites/${siteId}/stories`
