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
import BrokerClientSeats from '../pages/broker/BrokerClientSeats'
import BrokerTeam from '../pages/broker/BrokerTeam'
import BrokerExternalClients from '../pages/broker/BrokerExternalClients'
import BrokerExternalClientDetail from '../pages/broker/BrokerExternalClientDetail'

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
        <Route path="seats" element={<BrokerClientSeats />} />
        <Route path="team" element={<BrokerTeam />} />
        <Route path="pipeline" element={<BrokerPipeline />} />
        <Route path="referrals" element={<BrokerReferralLinks />} />
        <Route path="settings" element={<BrokerSettings />} />
        <Route path="clients/:companyId" element={<BrokerClientDetail />} />

        {/* Broker Pro — off-platform (non-tenant) clients */}
        <Route path="external" element={<BrokerExternalClients />} />
        <Route path="external/:clientId" element={<BrokerExternalClientDetail />} />

        {/* Legacy routes → new homes (preserve emailed links + bookmarks) */}
        <Route path="wc-portfolio" element={<Navigate to="/broker" replace />} />
        <Route path="risk-alerts" element={<Navigate to="/broker/action-center?tab=alerts" replace />} />
        {/* benefits/* (Renewals + Eligibility) redirects removed 2026-06-08 — those
            EB-broker tabs were paused; the legacy URLs now fall through. */}
      </Route>
    </Routes>
  )
}
