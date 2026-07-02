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

function Protected({ children, requireType }: { children: React.ReactNode; requireType?: 'consumer' | 'brand' }) {
  const { account, loading } = useAccount()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to="/login" replace />
  if (requireType && account.account_type !== requireType) {
    return <Navigate to={account.account_type === 'brand' ? '/brand/feedback' : '/'} replace />
  }
  return <Layout>{children}</Layout>
}

function Home() {
  const { account, loading } = useAccount()
  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (!account) return <Navigate to="/login" replace />
  if (account.account_type === 'brand') return <Navigate to="/brand/feedback" replace />
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
      <Route path="/brand/feedback" element={<Protected requireType="brand"><BrandFeedback /></Protected>} />
      <Route path="/brand/stores" element={<Protected requireType="brand"><BrandStores /></Protected>} />
      <Route path="/brand/listings" element={<Protected requireType="brand"><BrandListings /></Protected>} />
      <Route path="/brand/settings" element={<Protected requireType="brand"><BrandSettings /></Protected>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
