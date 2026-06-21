import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { applyBrokerTheme, getBrokerTheme, clearBrokerThemeAttr } from '../utils/brokerTheme'
import AppLayout from '../layouts/AppLayout'
import BrokerSidebar from '../components/BrokerSidebar'
import BrokerDashboard from '../pages/broker/BrokerDashboard'
import BrokerClientsHub from '../pages/broker/BrokerClientsHub'
import BrokerAccount from '../pages/broker/BrokerAccount'
import BrokerClientDetail from '../pages/broker/BrokerClientDetail'
import BrokerActionCenter from '../pages/broker/BrokerActionCenter'
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

        {/* Module 3 — Clients hub (tabbed: onboarding / pipeline / seats / referrals) */}
        <Route path="clients" element={<BrokerClientsHub />} />
        <Route path="clients/:companyId" element={<BrokerClientDetail />} />

        {/* Module 4 — Account hub (tabbed: team / settings) */}
        <Route path="account" element={<BrokerAccount />} />

        {/* Broker Pro — off-platform (non-tenant) clients */}
        <Route path="external" element={<BrokerExternalClients />} />
        <Route path="external/:clientId" element={<BrokerExternalClientDetail />} />

        {/* Legacy routes → new tabbed homes (preserve emailed links + bookmarks) */}
        <Route path="seats" element={<Navigate to="/broker/clients?tab=seats" replace />} />
        <Route path="pipeline" element={<Navigate to="/broker/clients?tab=pipeline" replace />} />
        <Route path="referrals" element={<Navigate to="/broker/clients?tab=referrals" replace />} />
        <Route path="team" element={<Navigate to="/broker/account?tab=team" replace />} />
        <Route path="settings" element={<Navigate to="/broker/account?tab=settings" replace />} />
        <Route path="wc-portfolio" element={<Navigate to="/broker" replace />} />
        <Route path="risk-alerts" element={<Navigate to="/broker/action-center?tab=alerts" replace />} />
        {/* benefits/* (Renewals + Eligibility) redirects removed 2026-06-08 — those
            EB-broker tabs were paused; the legacy URLs now fall through. */}
      </Route>
    </Routes>
  )
}
