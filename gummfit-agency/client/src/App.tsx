import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { GumFitLanding } from './pages/GumFitLanding';

// Creator pages
import {
  CreatorDashboard,
  RevenueDashboard,
  ExpenseTracker,
  PlatformConnections,
  DealMarketplace,
  MyApplications,
  MyContracts,
} from './pages/creator';
import { CampaignOffers } from './pages/creator/CampaignOffers';
import { AffiliateDashboard } from './pages/creator/AffiliateDashboard';

// Agency pages
import {
  AgencyDashboard,
  DealManager,
  CreatorDiscovery,
  ApplicationReview,
  ContractManager,
} from './pages/agency';
import { CampaignManager } from './pages/agency/CampaignManager';
import { CampaignDetail } from './pages/agency/CampaignDetail';
import { CreatorProfile } from './pages/agency/CreatorProfile';

// GumFit admin pages
import { GumFitDashboard } from './pages/gumfit/GumFitDashboard';
import { GumFitCreators } from './pages/gumfit/GumFitCreators';
import { GumFitAgencies } from './pages/gumfit/GumFitAgencies';
import { GumFitUsers } from './pages/gumfit/GumFitUsers';
import { GumFitInvites } from './pages/gumfit/GumFitInvites';
import { GumFitAssets } from './pages/gumfit/GumFitAssets';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register/:type" element={<Register />} />
        <Route path="/register" element={<Navigate to="/register/creator" replace />} />
        <Route path="/gumfit-landing" element={<GumFitLanding />} />

        {/* Authenticated routes */}
        <Route path="/app/gumfit" element={<Layout />}>
          {/* Creator routes */}
          <Route index element={<CreatorDashboard />} />
          <Route path="revenue" element={<RevenueDashboard />} />
          <Route path="expenses" element={<ExpenseTracker />} />
          <Route path="platforms" element={<PlatformConnections />} />
          <Route path="deals" element={<DealMarketplace />} />
          <Route path="applications" element={<MyApplications />} />
          <Route path="contracts" element={<MyContracts />} />
          <Route path="offers" element={<CampaignOffers />} />
          <Route path="affiliates" element={<AffiliateDashboard />} />

          {/* Agency routes */}
          <Route path="agency" element={<AgencyDashboard />} />
          <Route path="agency/deals" element={<DealManager />} />
          <Route path="agency/deals/new" element={<DealManager />} />
          <Route path="agency/creators" element={<CreatorDiscovery />} />
          <Route path="agency/creators/:id" element={<CreatorProfile />} />
          <Route path="agency/applications" element={<ApplicationReview />} />
          <Route path="agency/contracts" element={<ContractManager />} />
          <Route path="agency/campaigns" element={<CampaignManager />} />
          <Route path="agency/campaigns/:id" element={<CampaignDetail />} />

          {/* GumFit admin routes */}
          <Route path="admin" element={<GumFitDashboard />} />
          <Route path="admin/creators" element={<GumFitCreators />} />
          <Route path="admin/agencies" element={<GumFitAgencies />} />
          <Route path="admin/users" element={<GumFitUsers />} />
          <Route path="admin/invites" element={<GumFitInvites />} />
          <Route path="admin/assets" element={<GumFitAssets />} />
        </Route>

        {/* Default redirect */}
        <Route path="/" element={<Navigate to="/gumfit-landing" replace />} />
        <Route path="*" element={<Navigate to="/gumfit-landing" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
