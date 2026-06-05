import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { applyBrokerTheme, getBrokerTheme, clearBrokerThemeAttr } from '../utils/brokerTheme'
import AppLayout from '../layouts/AppLayout'
import BrokerSidebar from '../components/BrokerSidebar'
import BrokerDashboard from '../pages/broker/BrokerDashboard'
import BrokerClients from '../pages/broker/BrokerClients'
import BrokerPipeline from '../pages/broker/BrokerPipeline'
import BrokerSettings from '../pages/broker/BrokerSettings'
import BrokerClientDetail from '../pages/broker/BrokerClientDetail'
import BrokerReferralLinks from '../pages/broker/BrokerReferralLinks'
import BrokerActionCenter from '../pages/broker/BrokerActionCenter'

export default function BrokerRoutes() {
  // Apply the broker light/dark preference for the lifetime of any /broker route;
  // clear it on unmount so other surfaces stay dark.
  useEffect(() => {
    applyBrokerTheme(getBrokerTheme())
    return () => clearBrokerThemeAttr()
  }, [])

  return (
    <Routes>
      <Route element={<AppLayout sidebar={<BrokerSidebar />} logoLabel="Matcha Broker" />}>
        {/* Module 1 — Book of Business (account-performance master view) */}
        <Route index element={<BrokerDashboard />} />

        {/* Module 2 — Action Center (tabbed: alerts / renewals / eligibility / milestones) */}
        <Route path="action-center" element={<BrokerActionCenter />} />

        {/* Module 3 — Administration */}
        <Route path="clients" element={<BrokerClients />} />
        <Route path="pipeline" element={<BrokerPipeline />} />
        <Route path="referrals" element={<BrokerReferralLinks />} />
        <Route path="settings" element={<BrokerSettings />} />
        <Route path="clients/:companyId" element={<BrokerClientDetail />} />

        {/* Legacy routes → new homes (preserve emailed links + bookmarks) */}
        <Route path="wc-portfolio" element={<Navigate to="/broker" replace />} />
        <Route path="risk-alerts" element={<Navigate to="/broker/action-center?tab=alerts" replace />} />
        <Route path="benefits/eligibility-exceptions" element={<Navigate to="/broker/action-center?tab=eligibility" replace />} />
        <Route path="benefits/renewal-risk-radar" element={<Navigate to="/broker/action-center?tab=renewals" replace />} />
      </Route>
    </Routes>
  )
}
