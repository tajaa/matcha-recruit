import { Routes, Route } from 'react-router-dom'
import CappeLayout from './layout/CappeLayout'
import CappeLanding from './pages/CappeLanding'
import CappeSignup from './pages/CappeSignup'
import CappeLogin from './pages/CappeLogin'
import CappeVerify from './pages/CappeVerify'
import ClientThread from './pages/ClientThread'
import CappeBookingManage from './pages/CappeBookingManage'
import CappeSites from './pages/CappeSites'
import CappeOnboardingWizard from './onboarding/CappeOnboardingWizard'
import CappeTemplates from './pages/CappeTemplates'
import CappeSiteEditor from './pages/CappeSiteEditor'
import PageEditor from './pages/site/PageEditor'
import Shop from './pages/site/Shop'
import Orders from './pages/site/Orders'
import Subscribers from './pages/site/Subscribers'
import Campaigns from './pages/site/Campaigns'
import Forms from './pages/site/Forms'
import Bookings from './pages/site/Bookings'
import Locations from './pages/site/Locations'
import Blog from './pages/site/Blog'
import Messages from './pages/site/Messages'
import Clients from './pages/site/Clients'
import Reviews from './pages/site/Reviews'

// Cappe — website-builder product, served at /cappe. Self-contained route tree
// with its own auth (cappe_* tokens, useCappeMe). Public signup/login live
// OUTSIDE the CappeLayout gate; everything else is behind it. Each site exposes
// a tabbed workspace (pages, shop, orders, newsletter, forms, bookings, blog).
export default function CappeRoutes() {
  return (
    <Routes>
      {/* Public marketing landing — unlinked from any nav (hidden) for now. */}
      <Route index element={<CappeLanding />} />
      <Route path="website-setup" element={<CappeSignup />} />
      <Route path="login" element={<CappeLogin />} />
      <Route path="verify" element={<CappeVerify />} />
      {/* Public, token-gated client conversation (emailed link). */}
      <Route path="thread/:token" element={<ClientThread />} />
      {/* Public, token-gated booking self-serve (view / cancel / reschedule). */}
      <Route path="booking/:token" element={<CappeBookingManage />} />
      <Route element={<CappeLayout />}>
        {/* First-run business-setup wizard — CappeSites redirects here on zero sites. */}
        <Route path="onboarding" element={<CappeOnboardingWizard />} />
        <Route path="sites" element={<CappeSites />} />
        <Route path="templates" element={<CappeTemplates />} />
        <Route path="sites/:siteId" element={<CappeSiteEditor />} />
        <Route path="sites/:siteId/pages/:pageId" element={<PageEditor />} />
        <Route path="sites/:siteId/shop" element={<Shop />} />
        <Route path="sites/:siteId/orders" element={<Orders />} />
        <Route path="sites/:siteId/subscribers" element={<Subscribers />} />
        <Route path="sites/:siteId/campaigns" element={<Campaigns />} />
        <Route path="sites/:siteId/forms" element={<Forms />} />
        <Route path="sites/:siteId/bookings" element={<Bookings />} />
        <Route path="sites/:siteId/locations" element={<Locations />} />
        <Route path="sites/:siteId/messages" element={<Messages />} />
        <Route path="sites/:siteId/clients" element={<Clients />} />
        <Route path="sites/:siteId/reviews" element={<Reviews />} />
        <Route path="sites/:siteId/blog" element={<Blog />} />
      </Route>
    </Routes>
  )
}
