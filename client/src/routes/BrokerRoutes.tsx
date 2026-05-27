import { Routes, Route } from 'react-router-dom'
import AppLayout from '../layouts/AppLayout'
import BrokerSidebar from '../components/BrokerSidebar'
import BrokerDashboard from '../pages/broker/BrokerDashboard'
import BrokerClients from '../pages/broker/BrokerClients'
import BrokerSettings from '../pages/broker/BrokerSettings'
import BrokerWcPortfolio from '../pages/broker/BrokerWcPortfolio'
import BrokerClientDetail from '../pages/broker/BrokerClientDetail'
import BrokerReferralLinks from '../pages/broker/BrokerReferralLinks'
import BrokerRiskAlerts from '../pages/broker/BrokerRiskAlerts'

export default function BrokerRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout sidebar={<BrokerSidebar />} logoLabel="Matcha Broker" />}>
        <Route index element={<BrokerDashboard />} />
        <Route path="clients" element={<BrokerClients />} />
        <Route path="wc-portfolio" element={<BrokerWcPortfolio />} />
        <Route path="risk-alerts" element={<BrokerRiskAlerts />} />
        <Route path="referrals" element={<BrokerReferralLinks />} />
        <Route path="settings" element={<BrokerSettings />} />
        <Route path="clients/:companyId" element={<BrokerClientDetail />} />
      </Route>
    </Routes>
  )
}
