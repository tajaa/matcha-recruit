import { Suspense, lazy, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAccount } from './hooks/useAccount'
import { Layout } from './components/Layout'
import { Spinner } from './components/ui'
import { tellusApi } from './api/tellusClient'
import type { InboxBrand } from './api/types'

import Landing from './pages/Landing'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Verify from './pages/Verify'
import Intake from './pages/Intake'
import PublicBrand from './pages/PublicBrand'
import Places from './pages/Places'
import Claim from './pages/Claim'
import Scan from './pages/Scan'
import CardView from './pages/consumer/CardView'

import Rewards from './pages/consumer/Rewards'
import Marketplace from './pages/consumer/Marketplace'
import Redemptions from './pages/consumer/Redemptions'
import Leaderboard from './pages/consumer/Leaderboard'
import ConsumerSettings from './pages/consumer/Settings'
import MyReviews from './pages/consumer/MyReviews'
import Boards from './pages/consumer/Boards'
import BoardFeed from './pages/consumer/BoardFeed'
import Messages from './pages/Messages'

import BrandFeedback from './pages/brand/Feedback'
import BrandStores from './pages/brand/Stores'
import BrandListings from './pages/brand/Listings'
import BrandCampaigns from './pages/brand/Campaigns'
import BrandSettings from './pages/brand/Settings'
import BrandBilling from './pages/brand/Billing'
import BrandBoard from './pages/brand/Board'

// Konva + the designer tree are ~200KB of the bundle and only a brand that is
// actually laying out a flyer ever needs them — keep them out of first paint
// for every other surface (including the consumer app).
const CampaignDesigner = lazy(() => import('./pages/brand/CampaignDesigner'))

import TellusAdminUpdates from './pages/admin/Updates'
import AdminAccounts from './pages/admin/Accounts'
import AdminAccountDetail from './pages/admin/AccountDetail'
import AdminBrands from './pages/admin/Brands'
import AdminBrandDetail from './pages/admin/BrandDetail'
import AdminClaims from './pages/admin/Claims'
import AdminModeration from './pages/admin/Moderation'
import AdminEconomy from './pages/admin/Economy'
import AdminAudit from './pages/admin/Audit'
import ResetPassword from './pages/ResetPassword'

// Where an authenticated brand lands: /brand/billing if unpaid (or plan_status
// unset — a defensive fallback, e.g. mid-migration data), else the dashboard.
function brandHome(planStatus: string | null | undefined) {
  return planStatus === 'active' ? '/brand/feedback' : '/brand/billing'
}

function Protected({
  children, requireType, allowUnpaid, allowConsumerModerator, bare,
}: {
  children: React.ReactNode
  requireType?: 'consumer' | 'brand'
  allowUnpaid?: boolean
  // Lets a consumer-typed account (added as a team moderator via POST
  // /board/team) through a requireType="brand" gate. They have no brand_id
  // of their own — GET /me/moderated-brands is what the page uses to find
  // the board it moderates — so the plan_status/unpaid check below only
  // applies to true brand accounts.
  allowConsumerModerator?: boolean
  // Skip the <Layout> nav/sidebar chrome — for full-screen views like the
  // reward-card QR display, meant to be read at a glance on a counter/phone.
  bare?: boolean
}) {
  const { account, loading } = useAccount()
  const location = useLocation()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to={'/login?returnTo=' + encodeURIComponent(location.pathname + location.search)} replace />
  const isConsumerModerator = allowConsumerModerator && account.account_type === 'consumer'
  if (requireType && account.account_type !== requireType && !isConsumerModerator) {
    return <Navigate to={account.account_type === 'brand' ? brandHome(account.plan_status) : '/'} replace />
  }
  if (requireType === 'brand' && !isConsumerModerator && !allowUnpaid && account.plan_status !== 'active') {
    return <Navigate to="/brand/billing" replace />
  }
  return bare ? <>{children}</> : <Layout>{children}</Layout>
}

function CommsProtected({ children }: { children: React.ReactNode }) {
  const { account, loading } = useAccount()
  const location = useLocation()
  const [allowed, setAllowed] = useState<boolean | null>(null)
  useEffect(() => {
    if (!account) { setAllowed(false); return }
    if (account.account_type === 'brand') { setAllowed(true); return }
    tellusApi.get<InboxBrand[]>('/comms/inbox-brands').then(rows => setAllowed(rows.some(row => row.plan_status === 'active'))).catch(() => setAllowed(false))
  }, [account?.id, account?.account_type, account?.plan_status])
  if (loading || allowed === null) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to={'/login?returnTo=' + encodeURIComponent(location.pathname + location.search)} replace />
  if (!allowed) return <Navigate to={account.account_type === 'brand' ? brandHome(account.plan_status) : '/messages'} replace />
  return <Layout>{children}</Layout>
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  const { account, loading } = useAccount()
  const location = useLocation()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to={'/login?returnTo=' + encodeURIComponent(location.pathname + location.search)} replace />
  if (!account.is_admin) return <Navigate to="/" replace />
  return <Layout>{children}</Layout>
}

function Home() {
  const { account, loading } = useAccount()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to="/login" replace />
  if (account.account_type === 'brand') return <Navigate to={brandHome(account.plan_status)} replace />
  return <Protected requireType="consumer"><Rewards /></Protected>
}

// Places is public (marketing entry, e.g. from Landing) but shell-wrapped for
// a signed-in consumer so the new nav entry doesn't dump them out of the app
// chrome. Unlike Protected/AdminOnly, this never redirects — logged-out and
// brand accounts both just get the bare page.
function PlacesRoute() {
  const { account, loading } = useAccount()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (account?.account_type === 'consumer') return <Layout><Places /></Layout>
  return <Places />
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/tellus-app" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/verify" element={<Verify />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/i/:token" element={<Intake />} />
      <Route path="/b/:slug" element={<PublicBrand />} />
      <Route path="/places" element={<PlacesRoute />} />
      <Route path="/p/:token" element={<Claim />} />
      <Route path="/scan/:deviceToken" element={<Scan />} />

      {/* Consumer */}
      <Route path="/" element={<Home />} />
      <Route path="/marketplace" element={<Protected requireType="consumer"><Marketplace /></Protected>} />
      <Route path="/redemptions" element={<Protected requireType="consumer"><Redemptions /></Protected>} />
      <Route path="/my-reviews" element={<Protected requireType="consumer"><MyReviews /></Protected>} />
      <Route path="/boards" element={<Protected requireType="consumer"><Boards /></Protected>} />
      <Route path="/boards/:slug" element={<Protected><BoardFeed /></Protected>} />
      <Route path="/messages" element={<Protected requireType="consumer"><Messages /></Protected>} />
      <Route path="/leaderboard" element={<Protected requireType="consumer"><Leaderboard /></Protected>} />
      <Route path="/settings" element={<Protected requireType="consumer"><ConsumerSettings /></Protected>} />
      <Route path="/card/:cardToken" element={<Protected requireType="consumer" bare><CardView /></Protected>} />

      {/* Brand */}
      <Route path="/brand/billing" element={<Protected requireType="brand" allowUnpaid><BrandBilling /></Protected>} />
      <Route path="/brand/feedback" element={<Protected requireType="brand"><BrandFeedback /></Protected>} />
      <Route path="/brand/messages" element={<CommsProtected><Messages /></CommsProtected>} />
      <Route path="/brand/stores" element={<Protected requireType="brand"><BrandStores /></Protected>} />
      <Route path="/brand/listings" element={<Protected requireType="brand"><BrandListings /></Protected>} />
      <Route path="/brand/campaigns" element={<Protected requireType="brand"><BrandCampaigns /></Protected>} />
      {/* bare: the designer is a full-screen editor with its own chrome. */}
      <Route path="/brand/campaigns/:id/design" element={
        <Protected requireType="brand" bare>
          <Suspense fallback={<div className="min-h-screen bg-tu-bg"><Spinner /></div>}>
            <CampaignDesigner />
          </Suspense>
        </Protected>
      } />
      <Route path="/brand/board" element={<Protected requireType="brand" allowConsumerModerator><BrandBoard /></Protected>} />
      <Route path="/brand/settings" element={<Protected requireType="brand"><BrandSettings /></Protected>} />

      {/* Internal admin */}
      <Route path="/admin/accounts" element={<AdminOnly><AdminAccounts /></AdminOnly>} />
      <Route path="/admin/accounts/:id" element={<AdminOnly><AdminAccountDetail /></AdminOnly>} />
      <Route path="/admin/brands" element={<AdminOnly><AdminBrands /></AdminOnly>} />
      <Route path="/admin/brands/:id" element={<AdminOnly><AdminBrandDetail /></AdminOnly>} />
      <Route path="/admin/claims" element={<AdminOnly><AdminClaims /></AdminOnly>} />
      <Route path="/admin/moderation" element={<AdminOnly><AdminModeration /></AdminOnly>} />
      <Route path="/admin/economy" element={<AdminOnly><AdminEconomy /></AdminOnly>} />
      <Route path="/admin/updates" element={<AdminOnly><TellusAdminUpdates /></AdminOnly>} />
      <Route path="/admin/audit" element={<AdminOnly><AdminAudit /></AdminOnly>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
