import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import RequireRole from '../components/auth/RequireRole'
import AppLayout from '../layouts/AppLayout'
import AdminSidebar from '../components/sidebars/AdminSidebar'
import Companies from '../pages/admin/Companies'
import AdminCompanyDetail from '../pages/admin/company-detail'
import Features from '../pages/admin/Features'
import Settings from '../pages/admin/Settings'
import JurisdictionData from '../pages/admin/JurisdictionData'
import WcRateData from '../pages/admin/WcRateData'
import PayerData from '../pages/admin/PayerData'
import ComplianceStudio from '../pages/admin/studio/ComplianceStudio'
import Automation from '../pages/admin/Automation'
import Brokers from '../pages/admin/Brokers'
import FractionalHR from '../pages/admin/FractionalHR'
import FractionalClientDetail from '../pages/admin/FractionalClientDetail'
import DealFlow from '../pages/admin/DealFlow'
import MatchaLiteAdmin from '../pages/admin/MatchaLiteAdmin'
import ComplianceManagement from '../pages/admin/ComplianceManagement'
import MatchaWork from '../pages/admin/MatchaWork'
import Customers from '../pages/admin/Customers'
import Updates from '../pages/admin/Updates'
import Cappe from '../pages/admin/Cappe'
import GapAnalysisHome from '../pages/admin/GapAnalysisHome'
import AdminOnboardingWizard from '../pages/admin/AdminOnboardingWizard'
import GapDashboard from '../pages/admin/GapDashboard'
import GapAnalysisReport from '../components/admin/onboarding/GapAnalysisReport'
import ClientErrors from '../pages/admin/ClientErrors'
import ServerErrors from '../pages/admin/ServerErrors'
import TrafficReport from '../pages/admin/TrafficReport'
import Usage from '../pages/admin/Usage'
import NewsletterAdmin from '../pages/admin/newsletter'
import LandingMediaAdmin from '../pages/admin/LandingMedia'
import Blogs from '../pages/admin/Blogs'
import CategoryDetailPage from '../pages/admin/CategoryDetailPage'
import PolicyDetailPage from '../pages/admin/PolicyDetailPage'

// Old /admin/jurisdictions + /admin/scope-studio bookmarks/deep-links →
// unified /admin/studio, preserving any query params (e.g. scope-studio's
// ?state=&city=&industry= coordinate) onto the target view.
function StudioRedirect({ view }: { view: string }) {
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  params.set('view', view)
  return <Navigate to={`/admin/studio?${params.toString()}`} replace />
}

export default function AdminRoutes() {
  return (
    <RequireRole roles={['admin']}>
      <Routes>
      <Route element={<AppLayout sidebar={<AdminSidebar />} logoLabel="Matcha Admin" variant="admin" />}>
        <Route index element={<Navigate to="customers" replace />} />
        <Route path="updates" element={<Updates />} />
        <Route path="customers" element={<Customers />} />
        <Route path="gap-analysis" element={<GapAnalysisHome />} />
        <Route path="gap-analysis/company/:companyId" element={<GapDashboard />} />
        <Route path="gap-analysis/:sessionId" element={<AdminOnboardingWizard />} />
        <Route path="gap-analysis/:sessionId/report" element={<GapAnalysisReport />} />
        {/* legacy /admin/onboarding bookmarks → gap-analysis */}
        <Route path="onboarding" element={<Navigate to="/admin/gap-analysis" replace />} />
        <Route path="onboarding/*" element={<Navigate to="/admin/gap-analysis" replace />} />
        <Route path="companies" element={<Companies />} />
        <Route path="companies/:companyId" element={<AdminCompanyDetail />} />
        <Route path="matcha-work" element={<MatchaWork />} />
        <Route path="cappe" element={<Cappe />} />
        <Route path="individuals" element={<Navigate to="/admin/matcha-work" replace />} />
        <Route path="client-errors" element={<ClientErrors />} />
        <Route path="server-errors" element={<ServerErrors />} />
        <Route path="traffic" element={<TrafficReport />} />
        <Route path="usage" element={<Usage />} />
        <Route path="features" element={<Features />} />
        <Route path="settings" element={<Settings />} />
        <Route path="jurisdiction-data" element={<JurisdictionData />} />
        <Route path="wc-rate-data" element={<WcRateData />} />
        <Route path="jurisdiction-data/category/:slug" element={<CategoryDetailPage />} />
        <Route path="jurisdiction-data/policy/:id" element={<PolicyDetailPage />} />
        <Route path="payer-data" element={<PayerData />} />
        <Route path="studio" element={<ComplianceStudio />} />
        <Route path="automation" element={<Automation />} />
        <Route path="jurisdictions" element={<StudioRedirect view="pipeline" />} />
        <Route path="scope-studio" element={<StudioRedirect view="coverage" />} />
        <Route path="brokers" element={<Brokers />} />
        <Route path="fractional-hr" element={<FractionalHR />} />
        <Route path="fractional-hr/:clientId" element={<FractionalClientDetail />} />
        <Route path="deal-flow" element={<DealFlow />} />
        <Route path="matcha-lite" element={<MatchaLiteAdmin />} />
        <Route path="compliance-mgmt" element={<ComplianceManagement />} />
        <Route path="newsletter" element={<NewsletterAdmin />} />
        <Route path="newsletter/composer" element={<NewsletterAdmin />} />
        <Route path="landing-media" element={<LandingMediaAdmin />} />
        <Route path="blogs" element={<Blogs />} />
        <Route path="blogs/composer" element={<Blogs />} />
      </Route>
      </Routes>
    </RequireRole>
  )
}
