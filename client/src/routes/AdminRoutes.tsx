import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import RequireRole from '../components/auth/RequireRole'
import AppLayout from '../layouts/AppLayout'
import AdminLayout from '../layouts/AdminLayout'
import AdminSidebar from '../components/sidebars/AdminSidebar'
import Companies from '../pages/admin/customers/Companies'
import TestAccounts from '../pages/admin/customers/TestAccounts'
import AdminCompanyDetail from '../pages/admin/customers/company-detail'
import Features from '../pages/admin/customers/Features'
import Settings from '../pages/admin/platform/Settings'
import JurisdictionData from '../pages/admin/compliance/JurisdictionData'
import WcRateData from '../pages/admin/compliance/WcRateData'
import PayerData from '../pages/admin/compliance/PayerData'
import ComplianceStudio from '../pages/admin/compliance/studio/ComplianceStudio'
import Automation from '../pages/admin/platform/Automation'
import FractionalHR from '../pages/admin/customers/fractional-hr/FractionalHR'
import FractionalClientDetail from '../pages/admin/customers/fractional-hr/FractionalClientDetail'
import DealFlow from '../pages/admin/sales/DealFlow'
import SignupLinks from '../pages/admin/catalog/SignupLinks'
import Products from '../pages/admin/catalog/Products'
import Pricing from '../pages/admin/catalog/Pricing'
import ComplianceManagement from '../pages/admin/compliance/ComplianceManagement'
import MatchaWork from '../pages/admin/customers/workspaces/MatchaWork'
import Customers from '../pages/admin/customers/Customers'
import Updates from '../pages/admin/updates/Updates'
import Cappe from '../pages/admin/customers/workspaces/Cappe'
import CappeCreators from '../pages/admin/customers/workspaces/CappeCreators'
import GapAnalysisHome from '../pages/admin/sales/gap-analysis/GapAnalysisHome'
import AdminOnboardingWizard from '../pages/admin/sales/gap-analysis/AdminOnboardingWizard'
import GapDashboard from '../pages/admin/sales/gap-analysis/GapDashboard'
import GapAnalysisReport from '../components/admin/onboarding/GapAnalysisReport'
import ClientErrors from '../pages/admin/monitoring/ClientErrors'
import ServerErrors from '../pages/admin/monitoring/ServerErrors'
import AiUsage from '../pages/admin/monitoring/AiUsage'
import TrafficReport from '../pages/admin/monitoring/TrafficReport'
import Usage from '../pages/admin/monitoring/Usage'
import NewsletterAdmin from '../pages/admin/marketing/newsletter'
import LandingMediaAdmin from '../pages/admin/marketing/LandingMedia'
import Blogs from '../pages/admin/marketing/blogs/Blogs'
import CategoryDetailPage from '../pages/admin/compliance/CategoryDetailPage'
import PolicyDetailPage from '../pages/admin/compliance/PolicyDetailPage'
import MatchaOps from '../pages/admin/customers/workspaces/MatchaOps'

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
      <Route element={<AdminLayout />}>
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
        <Route path="test-accounts" element={<TestAccounts />} />
        <Route path="companies/:companyId" element={<AdminCompanyDetail />} />
        <Route path="matcha-work" element={<MatchaWork />} />
        <Route path="matcha-ops" element={<MatchaOps />} />
        <Route path="cappe" element={<Cappe />} />
        <Route path="cappe-creators" element={<CappeCreators />} />
        <Route path="individuals" element={<Navigate to="/admin/matcha-work" replace />} />
        <Route path="client-errors" element={<ClientErrors />} />
        <Route path="server-errors" element={<ServerErrors />} />
        <Route path="ai-usage" element={<AiUsage />} />
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
        <Route path="fractional-hr" element={<FractionalHR />} />
        <Route path="fractional-hr/:clientId" element={<FractionalClientDetail />} />
        <Route path="deal-flow" element={<DealFlow />} />
        <Route path="matcha-lite" element={<SignupLinks />} />
        <Route path="products" element={<Products />} />
        <Route path="pricing" element={<Pricing />} />
        <Route path="compliance-mgmt" element={<ComplianceManagement />} />
        <Route path="newsletter" element={<NewsletterAdmin />} />
        <Route path="newsletter/composer" element={<NewsletterAdmin />} />
        <Route path="landing-media" element={<LandingMediaAdmin />} />
        <Route path="blogs" element={<Blogs />} />
        <Route path="blogs/composer" element={<Blogs />} />
      </Route>
      </Route>
      </Routes>
    </RequireRole>
  )
}
