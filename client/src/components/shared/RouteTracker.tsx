import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { trackPageView } from '../../utils/usageTracker'

/** Records a page view on every navigation. Mounted once beside <Routes> in
 *  App.tsx — that's the single seam every surface (app, admin, work, werk,
 *  broker, portal, public) passes through. Renders nothing. */
export default function RouteTracker() {
  const { pathname } = useLocation()

  useEffect(() => {
    trackPageView(pathname)
  }, [pathname])

  return null
}
