import { Routes, Route } from 'react-router-dom'
import CappeLayout from '../layouts/CappeLayout'
import CappeSignup from '../pages/cappe/CappeSignup'
import CappeLogin from '../pages/cappe/CappeLogin'
import CappeSites from '../pages/cappe/CappeSites'
import CappeTemplates from '../pages/cappe/CappeTemplates'
import CappeSiteEditor from '../pages/cappe/CappeSiteEditor'
import Shop from '../pages/cappe/site/Shop'
import Orders from '../pages/cappe/site/Orders'
import Subscribers from '../pages/cappe/site/Subscribers'
import Campaigns from '../pages/cappe/site/Campaigns'
import Forms from '../pages/cappe/site/Forms'
import Bookings from '../pages/cappe/site/Bookings'
import Blog from '../pages/cappe/site/Blog'

// Cappe — website-builder product, served at /cappe. Self-contained route tree
// with its own auth (cappe_* tokens, useCappeMe). Public signup/login live
// OUTSIDE the CappeLayout gate; everything else is behind it. Each site exposes
// a tabbed workspace (pages, shop, orders, newsletter, forms, bookings, blog).
export default function CappeRoutes() {
  return (
    <Routes>
      <Route path="website-setup" element={<CappeSignup />} />
      <Route path="login" element={<CappeLogin />} />
      <Route element={<CappeLayout />}>
        <Route index element={<CappeSites />} />
        <Route path="templates" element={<CappeTemplates />} />
        <Route path="sites/:siteId" element={<CappeSiteEditor />} />
        <Route path="sites/:siteId/shop" element={<Shop />} />
        <Route path="sites/:siteId/orders" element={<Orders />} />
        <Route path="sites/:siteId/subscribers" element={<Subscribers />} />
        <Route path="sites/:siteId/campaigns" element={<Campaigns />} />
        <Route path="sites/:siteId/forms" element={<Forms />} />
        <Route path="sites/:siteId/bookings" element={<Bookings />} />
        <Route path="sites/:siteId/blog" element={<Blog />} />
      </Route>
    </Routes>
  )
}
