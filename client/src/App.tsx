import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing'
import MatchaWorkPage from './pages/landing/MatchaWorkPage'
import ServicesPage from './pages/landing/ServicesPage'
import Login from './pages/Login'
import AppLayout from './layouts/AppLayout'
import AdminSidebar from './components/AdminSidebar'
import TenantSidebar from './components/TenantSidebar'
import IrSignup from './pages/auth/IrSignup'
import ResourcesSignup from './pages/auth/ResourcesSignup'
import RequireBusinessAccount from './components/auth/RequireBusinessAccount'
import IrOnboardingWizard from './features/ir-onboarding/IrOnboardingWizard'
import AnonymousReport from './pages/shared/AnonymousReport'
import Companies from './pages/admin/Companies'
import AdminCompanyDetail from './pages/admin/AdminCompanyDetail'
import Features from './pages/admin/Features'
import Settings from './pages/admin/Settings'
import JurisdictionData from './pages/admin/JurisdictionData'
import PayerData from './pages/admin/PayerData'
import Jurisdictions from './pages/admin/Jurisdictions'
import IndustryRequirements from './pages/admin/IndustryRequirements'
import SpecializationResearch from './pages/admin/SpecializationResearch'
import Brokers from './pages/admin/Brokers'
import ComplianceManagement from './pages/admin/ComplianceManagement'
import Individuals from './pages/admin/Individuals'
import ClientErrors from './pages/admin/ClientErrors'
import ServerErrors from './pages/admin/ServerErrors'
import NewsletterAdmin from './pages/admin/Newsletter'
import LandingMediaAdmin from './pages/admin/LandingMedia'
import Blogs from './pages/admin/Blogs'
import Subscribe from './pages/landing/Subscribe'
import BlogIndex from './pages/landing/BlogIndex'
import BlogPostPage from './pages/landing/BlogPost'
import ResourcesHub from './pages/landing/ResourcesHub'
import ResourcesTemplates from './pages/landing/resources/Templates'
import ResourcesJobDescriptions from './pages/landing/resources/JobDescriptions'
import ResourcesGlossary from './pages/landing/resources/Glossary'
import ResourcesGlossaryTerm from './pages/landing/resources/GlossaryTerm'
import ResourcesStateGuides from './pages/landing/resources/StateGuides'
import ResourcesStateGuide from './pages/landing/resources/StateGuide'
import ResourcesCalculators from './pages/landing/resources/Calculators'
import CalcPtoAccrual from './pages/landing/resources/calculators/PtoAccrual'
import CalcTurnoverCost from './pages/landing/resources/calculators/TurnoverCost'
import ResourcesComplianceAudit from './pages/landing/resources/ComplianceAudit'
import CategoryDetailPage from './pages/admin/CategoryDetailPage'
import PolicyDetailPage from './pages/admin/PolicyDetailPage'
import Dashboard from './pages/app/Dashboard'
import Employees from './pages/app/Employees'
import Onboarding from './pages/app/Onboarding'
import ERCopilot from './pages/app/ERCopilot'
import ERCaseDetail from './pages/app/ERCaseDetail'
import Compliance from './pages/app/Compliance'
import EmployeeDetail from './pages/app/EmployeeDetail'
import IRList from './pages/app/IRList'
import IRDetail from './pages/app/IRDetail'
import Locations from './pages/app/Locations'
import Handbooks from './pages/app/Handbooks'
import HandbookDetail from './pages/app/HandbookDetail'
import HandbookForm from './pages/app/HandbookForm'
import Policies from './pages/app/Policies'
import RiskAssessment from './pages/app/RiskAssessment'
import CredentialTemplates from './pages/app/CredentialTemplates'
import Inbox from './pages/app/Inbox'
import UserSettings from './pages/app/UserSettings'
import Notifications from './pages/app/Notifications'
import EscalatedQueries from './pages/app/EscalatedQueries'
import Accommodations from './pages/app/Accommodations'
import AccommodationDetail from './pages/app/AccommodationDetail'
import CompanySettings from './pages/app/CompanySettings'
import Discipline from './pages/app/Discipline'
import DisciplineDetail from './pages/app/DisciplineDetail'
import DisciplineSettings from './pages/app/DisciplineSettings'
import { FeatureGate } from './components/FeatureGate'
import BrokerSidebar from './components/BrokerSidebar'
import BrokerDashboard from './pages/broker/BrokerDashboard'
import BrokerClients from './pages/broker/BrokerClients'
import BrokerSettings from './pages/broker/BrokerSettings'
import BrokerClientDetail from './pages/broker/BrokerClientDetail'
import ERExportDownload from './pages/shared/ERExportDownload'
import CandidateInterview from './pages/shared/CandidateInterview'
import SSOCallback from './pages/SSOCallback'
import BetaRegister from './pages/BetaRegister'
import ResetPassword from './pages/ResetPassword'
import WorkLayout from './layouts/WorkLayout'
import MatchaWorkList from './pages/work/MatchaWorkList'
import MatchaWorkThread from './pages/work/MatchaWorkThread'
import ProjectView from './pages/work/ProjectView'
import ChannelView from './pages/work/ChannelView'
import WorkEmail from './pages/work/WorkEmail'
import ChannelBrowse from './pages/work/ChannelBrowse'
import ChannelJoinByInvite from './pages/work/ChannelJoinByInvite'
import ChannelBilling from './pages/work/ChannelBilling'
import ConnectionsPanel from './components/work/ConnectionsPanel'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/matcha-work" element={<MatchaWorkPage />} />
      <Route path="/services" element={<ServicesPage />} />
      <Route path="/subscribe" element={<Subscribe />} />
      <Route path="/blog" element={<BlogIndex />} />
      <Route path="/blog/:slug" element={<BlogPostPage />} />
      <Route path="/resources" element={<ResourcesHub />} />
      <Route path="/resources/glossary" element={<ResourcesGlossary />} />
      <Route path="/resources/glossary/:slug" element={<ResourcesGlossaryTerm />} />
      <Route path="/resources/templates" element={<RequireBusinessAccount><ResourcesTemplates /></RequireBusinessAccount>} />
      <Route path="/resources/templates/job-descriptions" element={<RequireBusinessAccount><ResourcesJobDescriptions /></RequireBusinessAccount>} />
      <Route path="/resources/states" element={<RequireBusinessAccount><ResourcesStateGuides /></RequireBusinessAccount>} />
      <Route path="/resources/states/:slug" element={<RequireBusinessAccount><ResourcesStateGuide /></RequireBusinessAccount>} />
      <Route path="/resources/calculators" element={<RequireBusinessAccount><ResourcesCalculators /></RequireBusinessAccount>} />
      <Route path="/resources/calculators/pto-accrual" element={<RequireBusinessAccount><CalcPtoAccrual /></RequireBusinessAccount>} />
      <Route path="/resources/calculators/turnover-cost" element={<RequireBusinessAccount><CalcTurnoverCost /></RequireBusinessAccount>} />
      <Route path="/resources/audit" element={<RequireBusinessAccount><ResourcesComplianceAudit /></RequireBusinessAccount>} />
      <Route path="/auth/resources-signup" element={<ResourcesSignup />} />
      <Route path="/login" element={<Login />} />
      <Route path="/sso/callback" element={<SSOCallback />} />
      <Route path="/register/beta" element={<BetaRegister />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/s/:token" element={<ERExportDownload />} />
      <Route path="/candidate-interview/:token" element={<CandidateInterview />} />
      <Route path="/work" element={<WorkLayout />}>
        <Route index element={<MatchaWorkList />} />
        <Route path="inbox" element={<Inbox />} />
        <Route path="email" element={<WorkEmail />} />
        <Route path="billing" element={<ChannelBilling />} />
        <Route path="connections" element={<ConnectionsPanel />} />
        <Route path="channels" element={<ChannelBrowse />} />
        <Route path="channels/join/:code" element={<ChannelJoinByInvite />} />
        <Route path="channels/:channelId" element={<ChannelView />} />
        <Route path=":threadId" element={<MatchaWorkThread />} />
        <Route path="projects/:projectId" element={<ProjectView />} />
      </Route>
      <Route path="/admin" element={<AppLayout sidebar={<AdminSidebar />} />}>
        <Route index element={<Navigate to="companies" replace />} />
        <Route path="companies" element={<Companies />} />
        <Route path="companies/:companyId" element={<AdminCompanyDetail />} />
        <Route path="individuals" element={<Individuals />} />
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
        <Route path="compliance-mgmt" element={<ComplianceManagement />} />
        <Route path="newsletter" element={<NewsletterAdmin />} />
        <Route path="landing-media" element={<LandingMediaAdmin />} />
        <Route path="blogs" element={<Blogs />} />
      </Route>
      <Route path="/broker" element={<AppLayout sidebar={<BrokerSidebar />} />}>
        <Route index element={<BrokerDashboard />} />
        <Route path="clients" element={<BrokerClients />} />
        <Route path="settings" element={<BrokerSettings />} />
        <Route path="clients/:companyId" element={<BrokerClientDetail />} />
      </Route>
      <Route path="/ir/signup" element={<IrSignup />} />
      <Route path="/ir/onboarding" element={<IrOnboardingWizard />} />
      <Route path="/report/:token" element={<AnonymousReport />} />
      <Route path="/app" element={<AppLayout sidebar={<TenantSidebar />} />}>
        <Route index element={<Dashboard />} />
        <Route path="company" element={<CompanySettings />} />
        <Route path="employees" element={<Employees />} />
        <Route path="employees/:employeeId" element={<EmployeeDetail />} />
        <Route path="onboarding" element={<Onboarding />} />
        <Route path="er-copilot" element={<FeatureGate feature="er_copilot" label="ER Copilot"><ERCopilot /></FeatureGate>} />
        <Route path="er-copilot/:caseId" element={<FeatureGate feature="er_copilot" label="ER Copilot"><ERCaseDetail /></FeatureGate>} />
        <Route path="compliance" element={<FeatureGate feature="compliance" label="Compliance"><Compliance /></FeatureGate>} />
        <Route path="ir" element={<IRList />} />
        <Route path="ir/:incidentId" element={<IRDetail />} />
        <Route path="locations" element={<FeatureGate feature="incidents" label="Locations"><Locations /></FeatureGate>} />
        <Route path="escalated-queries" element={<EscalatedQueries />} />
        <Route path="accommodations" element={<FeatureGate feature="accommodations" label="Accommodations"><Accommodations /></FeatureGate>} />
        <Route path="accommodations/:caseId" element={<FeatureGate feature="accommodations" label="Accommodations"><AccommodationDetail /></FeatureGate>} />
        <Route path="discipline" element={<FeatureGate feature="discipline" label="Performance Action"><Discipline /></FeatureGate>} />
        <Route path="discipline/:recordId" element={<FeatureGate feature="discipline" label="Performance Action"><DisciplineDetail /></FeatureGate>} />
        <Route path="discipline-settings" element={<FeatureGate feature="discipline" label="Performance Action"><DisciplineSettings /></FeatureGate>} />
        <Route path="policies" element={<FeatureGate feature="policies" label="Policies"><Policies /></FeatureGate>} />
        <Route path="handbooks" element={<FeatureGate feature="handbooks" label="Handbooks"><Handbooks /></FeatureGate>} />
        <Route path="handbook/new" element={<FeatureGate feature="handbooks" label="Handbooks"><HandbookForm /></FeatureGate>} />
        <Route path="handbook/:id" element={<FeatureGate feature="handbooks" label="Handbooks"><HandbookDetail /></FeatureGate>} />
        <Route path="handbook/:id/edit" element={<FeatureGate feature="handbooks" label="Handbooks"><HandbookForm /></FeatureGate>} />
        <Route path="risk-assessment" element={<FeatureGate feature="risk_assessment" label="Risk Assessment"><RiskAssessment /></FeatureGate>} />
        <Route path="credential-templates" element={<FeatureGate feature="credential_templates" label="Credential Templates"><CredentialTemplates /></FeatureGate>} />
        <Route path="inbox" element={<Inbox />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="settings" element={<UserSettings />} />
      </Route>
    </Routes>
  )
}
