import { Navigate, Route, Routes } from 'react-router-dom'
import { useAccount } from './hooks/useAccount'
import { Layout } from './components/Layout'
import { Spinner } from './components/ui'

import Landing from './pages/Landing'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Verify from './pages/Verify'
import Intake from './pages/Intake'

import Rewards from './pages/consumer/Rewards'
import Marketplace from './pages/consumer/Marketplace'
import Redemptions from './pages/consumer/Redemptions'
import Leaderboard from './pages/consumer/Leaderboard'
import ConsumerSettings from './pages/consumer/Settings'

import BrandFeedback from './pages/brand/Feedback'
import BrandStores from './pages/brand/Stores'
import BrandListings from './pages/brand/Listings'
import BrandSettings from './pages/brand/Settings'
import BrandBilling from './pages/brand/Billing'

// Where an authenticated brand lands: /brand/billing if unpaid (or plan_status
// unset — a defensive fallback, e.g. mid-migration data), else the dashboard.
function brandHome(planStatus: string | null | undefined) {
  return planStatus === 'active' ? '/brand/feedback' : '/brand/billing'
}

function Protected({
  children, requireType, allowUnpaid,
}: { children: React.ReactNode; requireType?: 'consumer' | 'brand'; allowUnpaid?: boolean }) {
  const { account, loading } = useAccount()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to="/login" replace />
  if (requireType && account.account_type !== requireType) {
    return <Navigate to={account.account_type === 'brand' ? brandHome(account.plan_status) : '/'} replace />
  }
  if (requireType === 'brand' && !allowUnpaid && account.plan_status !== 'active') {
    return <Navigate to="/brand/billing" replace />
  }
  return <Layout>{children}</Layout>
}

function Home() {
  const { account, loading } = useAccount()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to="/login" replace />
  if (account.account_type === 'brand') return <Navigate to={brandHome(account.plan_status)} replace />
  return <Protected requireType="consumer"><Rewards /></Protected>
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/tellus-app" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/verify" element={<Verify />} />
      <Route path="/i/:token" element={<Intake />} />

      {/* Consumer */}
      <Route path="/" element={<Home />} />
      <Route path="/marketplace" element={<Protected requireType="consumer"><Marketplace /></Protected>} />
      <Route path="/redemptions" element={<Protected requireType="consumer"><Redemptions /></Protected>} />
      <Route path="/leaderboard" element={<Protected requireType="consumer"><Leaderboard /></Protected>} />
      <Route path="/settings" element={<Protected requireType="consumer"><ConsumerSettings /></Protected>} />

      {/* Brand */}
      <Route path="/brand/billing" element={<Protected requireType="brand" allowUnpaid><BrandBilling /></Protected>} />
      <Route path="/brand/feedback" element={<Protected requireType="brand"><BrandFeedback /></Protected>} />
      <Route path="/brand/stores" element={<Protected requireType="brand"><BrandStores /></Protected>} />
      <Route path="/brand/listings" element={<Protected requireType="brand"><BrandListings /></Protected>} />
      <Route path="/brand/settings" element={<Protected requireType="brand"><BrandSettings /></Protected>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
