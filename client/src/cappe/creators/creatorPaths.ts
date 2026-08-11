/** Canonical Gummfit Creators URLs. Legacy /cappe/creator routes stay mounted
 * for old email deep links, but new navigation should remain in this product. */
export const creatorPaths = {
  home: '/gummfit/creators/dashboard',
  deals: '/gummfit/creators/dashboard/deals',
  earnings: '/gummfit/creators/dashboard/earnings',
  directory: '/gummfit/creators/directory',
  login: '/gummfit/creators/login',
  signup: '/gummfit/creators/signup',
} as const

export const creatorDealPath = (offerId: string) => `${creatorPaths.deals}/${offerId}`
export const creatorProfilePath = (handle: string) => `/gummfit/creators/${handle}`
