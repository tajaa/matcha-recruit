import { cappePath } from '../host'

/** Canonical Gummfit Creators URLs. Legacy /cappe/creator routes stay mounted
 * for old email deep links, but new navigation should remain in this product. */
export const creatorPaths = {
  home: cappePath('/gummfit/creators/dashboard'),
  deals: cappePath('/gummfit/creators/dashboard/deals'),
  earnings: cappePath('/gummfit/creators/dashboard/earnings'),
  directory: cappePath('/gummfit/creators/directory'),
  login: cappePath('/gummfit/creators/login'),
  signup: cappePath('/gummfit/creators/signup'),
  brandHome: cappePath('/gummfit/creators/brands/dashboard'),
  brandCollabs: cappePath('/gummfit/creators/brands/dashboard/collabs'),
  brandLogin: cappePath('/gummfit/creators/brands/login'),
  brandSignup: cappePath('/gummfit/creators/brands/signup'),
} as const

export const creatorDealPath = (offerId: string) => `${creatorPaths.deals}/${offerId}`
export const brandCollabPath = (offerId: string) => `${creatorPaths.brandCollabs}/${offerId}`
export const creatorProfilePath = (handle: string) => cappePath(`/gummfit/creators/${handle}`)
