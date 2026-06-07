import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from '../layouts/AppLayout'
import AdminSidebar from '../components/AdminSidebar'
import Companies from '../pages/admin/Companies'
import AdminCompanyDetail from '../pages/admin/AdminCompanyDetail'
import Features from '../pages/admin/Features'
import Settings from '../pages/admin/Settings'
import JurisdictionData from '../pages/admin/JurisdictionData'
import PayerData from '../pages/admin/PayerData'
import Jurisdictions from '../pages/admin/Jurisdictions'
import IndustryRequirements from '../pages/admin/IndustryRequirements'
import SpecializationResearch from '../pages/admin/SpecializationResearch'
import Brokers from '../pages/admin/Brokers'
import FractionalHR from '../pages/admin/FractionalHR'
import FractionalClientDetail from '../pages/admin/FractionalClientDetail'
import DealFlow from '../pages/admin/DealFlow'
import MatchaLiteAdmin from '../pages/admin/MatchaLiteAdmin'
import ComplianceManagement from '../pages/admin/ComplianceManagement'
import MatchaWork from '../pages/admin/MatchaWork'
import Customers from '../pages/admin/Customers'
import GapAnalysisHome from '../pages/admin/GapAnalysisHome'
import AdminOnboardingWizard from '../pages/admin/AdminOnboardingWizard'
import GapDashboard from '../pages/admin/GapDashboard'
import GapAnalysisReport from '../features/admin-onboarding/GapAnalysisReport'
import ClientErrors from '../pages/admin/ClientErrors'
import ServerErrors from '../pages/admin/ServerErrors'
import NewsletterAdmin from '../pages/admin/Newsletter'
import LandingMediaAdmin from '../pages/admin/LandingMedia'
import Blogs from '../pages/admin/Blogs'
import CategoryDetailPage from '../pages/admin/CategoryDetailPage'
import PolicyDetailPage from '../pages/admin/PolicyDetailPage'

export default function AdminRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout sidebar={<AdminSidebar />} logoLabel="Matcha Admin" />}>
        <Route index element={<Navigate to="customers" replace />} />
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
        <Route path="individuals" element={<Navigate to="/admin/matcha-work" replace />} />
        <Route path="client-errors" element={<ClientErrors />} />
        <Route path="server-errors" element={<ServerErrors />} />
        <Route path="features" element={<Features />} />
        <Route path="settings" element={<Settings />} />
        <Route path="jurisdiction-data" element={<JurisdictionData />} />
        <Route path="jurisdiction-data/category/:slug" element={<CategoryDetailPage />} />
        <Route path="jurisdiction-data/policy/:id" element={<PolicyDetailPage />} />
        <Route path="payer-data" element={<PayerData />} />
        <Route path="jurisdictions" element={<Jurisdictions />} />
        <Route path="industry-requirements" element={<IndustryRequirements />} />
        <Route path="specialization-research" element={<SpecializationResearch />} />
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
  )
}
