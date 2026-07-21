import { lazy, Suspense } from 'react'
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

// The site-builder sub-tree, lazily. PageEditor alone is ~1.5k LOC of canvas
// editor, and every one of these was eager — so hitting /cappe/login downloaded
// the entire builder before rendering a login form. These are all behind
// :siteId routes an authenticated user navigates to deliberately.
const PageEditor = lazy(() => import('./pages/site/PageEditor'))
const Shop = lazy(() => import('./pages/site/Shop'))
const Orders = lazy(() => import('./pages/site/Orders'))
const Subscribers = lazy(() => import('./pages/site/Subscribers'))
const Campaigns = lazy(() => import('./pages/site/Campaigns'))
const Forms = lazy(() => import('./pages/site/Forms'))
const Bookings = lazy(() => import('./pages/site/Bookings'))
const Locations = lazy(() => import('./pages/site/Locations'))
const Blog = lazy(() => import('./pages/site/Blog'))
const Messages = lazy(() => import('./pages/site/Messages'))
const Clients = lazy(() => import('./pages/site/Clients'))
const Reviews = lazy(() => import('./pages/site/Reviews'))

// Cappe — website-builder product, served at /cappe. Self-contained route tree
// with its own auth (cappe_* tokens, useCappeMe). Public signup/login live
// OUTSIDE the CappeLayout gate; everything else is behind it. Each site exposes
// a tabbed workspace (pages, shop, orders, newsletter, forms, bookings, blog).
export default function CappeRoutes() {
  return (
    // One boundary around the tree: only the lazy site/* routes suspend, and
    // they all render inside CappeLayout, so the chrome stays put and just the
    // body swaps to this line.
    <Suspense fallback={<div className="p-8 text-sm text-zinc-500">Loading…</div>}>
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
    </Suspense>
  )
}
