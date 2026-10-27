/** Where a launch-checklist item's "Do this" opens (services/readiness.py's
 *  `action`). `homePageId` is the page the page-editing items open; without
 *  one they open the site's dashboard. */
export function readinessActionPath(siteId: string, action: string | null, homePageId?: string): string {
  switch (action) {
    case 'shop': return `/cappe/sites/${siteId}/shop`
    case 'pages': return homePageId ? `/cappe/sites/${siteId}/pages/${homePageId}` : `/cappe/sites/${siteId}`
    case 'settings': return `/cappe/sites/${siteId}`
    // The commerce items: the Shop page's settings cards, and Orders for Stripe.
    case 'policies': case 'shipping': case 'tax': case 'identity':
      return `/cappe/sites/${siteId}/shop#${action}`
    case 'payments': return `/cappe/sites/${siteId}/orders`
    // A magazine site's checklist (services/readiness.py).
    case 'stories': return `/cappe/sites/${siteId}/stories`
    case 'magazine': return `/cappe/sites/${siteId}/magazine`
    case 'billing': return '/cappe/billing'
    default: return `/cappe/sites/${siteId}`
  }
}
