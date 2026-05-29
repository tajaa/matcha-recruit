import { Routes, Route } from 'react-router-dom'
import AppLayout from '../layouts/AppLayout'
import TenantSidebar from '../components/TenantSidebar'
import { FeatureGate } from '../components/FeatureGate'
import RequireBusinessAccount from '../components/auth/RequireBusinessAccount'
import Dashboard from '../pages/app/Dashboard'
import Employees from '../pages/app/Employees'
import Onboarding from '../pages/app/Onboarding'
import ERCopilot from '../pages/app/ERCopilot'
import ERCaseDetail from '../pages/app/ERCaseDetail'
import Compliance from '../pages/app/Compliance'
import ComplianceCalendar from '../pages/app/ComplianceCalendar'
import EmployeeDetail from '../pages/app/EmployeeDetail'
import IRList from '../pages/app/IRList'
import IRDetail from '../pages/app/IRDetail'
import IRRiskInsights from '../pages/app/IRRiskInsights'
import IRPersonDetail from '../pages/app/IRPersonDetail'
import OshaLogs from '../pages/app/OshaLogs'
import Locations from '../pages/app/Locations'
import Handbooks from '../pages/app/Handbooks'
import HandbookDetail from '../pages/app/HandbookDetail'
import HandbookForm from '../pages/app/HandbookForm'
import AskExpert from '../pages/app/AskExpert'
import Policies from '../pages/app/Policies'
import RiskAssessment from '../pages/app/RiskAssessment'
import CredentialTemplates from '../pages/app/CredentialTemplates'
import Inbox from '../pages/app/Inbox'
import UserSettings from '../pages/app/UserSettings'
import Notifications from '../pages/app/Notifications'
import EscalatedQueries from '../pages/app/EscalatedQueries'
import Accommodations from '../pages/app/Accommodations'
import AccommodationDetail from '../pages/app/AccommodationDetail'
import CompanySettings from '../pages/app/CompanySettings'
import Discipline from '../pages/app/Discipline'
import DisciplineDetail from '../pages/app/DisciplineDetail'
import DisciplineSettings from '../pages/app/DisciplineSettings'
import Training from '../pages/app/Training'
import TrainingDetail from '../pages/app/TrainingDetail'
import AppResources from '../pages/app/AppResources'
import ResourcesTemplates from '../pages/landing/resources/Templates'
import ResourcesJobDescriptions from '../pages/landing/resources/JobDescriptions'
import JobDescriptionDetail from '../pages/landing/resources/JobDescriptionDetail'
import ResourcesGlossary from '../pages/landing/resources/Glossary'
import ResourcesGlossaryTerm from '../pages/landing/resources/GlossaryTerm'
import ResourcesCalculators from '../pages/landing/resources/Calculators'
import CalcPtoAccrual from '../pages/landing/resources/calculators/PtoAccrual'
import CalcTurnoverCost from '../pages/landing/resources/calculators/TurnoverCost'
import CalcOvertime from '../pages/landing/resources/calculators/Overtime'
import CalcTotalComp from '../pages/landing/resources/calculators/TotalComp'
import ResourcesComplianceAudit from '../pages/landing/resources/ComplianceAudit'
import HandbookGapAnalyzer from '../pages/landing/HandbookGapAnalyzer'
import HandbookGapResult from '../pages/landing/HandbookGapResult'

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout sidebar={<TenantSidebar />} />}>
        <Route index element={<Dashboard />} />
        <Route path="company" element={<CompanySettings />} />
        <Route path="employees" element={<Employees />} />
        <Route path="employees/:employeeId" element={<EmployeeDetail />} />
        <Route path="onboarding" element={<Onboarding />} />
        <Route path="er-copilot" element={<FeatureGate feature="er_copilot" label="ER Copilot"><ERCopilot /></FeatureGate>} />
        <Route path="er-copilot/:caseId" element={<FeatureGate feature="er_copilot" label="ER Copilot"><ERCaseDetail /></FeatureGate>} />
        <Route path="compliance" element={<FeatureGate feature="compliance" label="Compliance"><Compliance /></FeatureGate>} />
        <Route path="compliance-calendar" element={<ComplianceCalendar />} />
        <Route path="ir" element={<IRList />} />
        <Route path="ir/risk-insights" element={<IRRiskInsights />} />
        <Route path="ir/osha" element={<OshaLogs />} />
        <Route path="ir/people/:personId" element={<IRPersonDetail />} />
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
        <Route path="training" element={<FeatureGate feature="training" label="Training"><Training /></FeatureGate>} />
        <Route path="training/:requirementId" element={<FeatureGate feature="training" label="Training"><TrainingDetail /></FeatureGate>} />
        <Route path="ask-expert" element={<AskExpert />} />
        <Route path="risk-assessment" element={<FeatureGate feature="risk_assessment" label="Risk Assessment"><RiskAssessment /></FeatureGate>} />
        <Route path="credential-templates" element={<FeatureGate feature="credential_templates" label="Credential Templates"><CredentialTemplates /></FeatureGate>} />
        <Route path="resources" element={<AppResources />} />
        <Route path="resources/templates" element={<RequireBusinessAccount><ResourcesTemplates embedded /></RequireBusinessAccount>} />
        <Route path="resources/templates/job-descriptions" element={<ResourcesJobDescriptions embedded />} />
        <Route path="resources/templates/job-descriptions/:slug" element={<JobDescriptionDetail embedded />} />
        <Route path="resources/calculators" element={<RequireBusinessAccount><ResourcesCalculators embedded /></RequireBusinessAccount>} />
        <Route path="resources/calculators/pto-accrual" element={<RequireBusinessAccount><CalcPtoAccrual embedded /></RequireBusinessAccount>} />
        <Route path="resources/calculators/turnover-cost" element={<RequireBusinessAccount><CalcTurnoverCost embedded /></RequireBusinessAccount>} />
        <Route path="resources/calculators/overtime" element={<RequireBusinessAccount><CalcOvertime embedded /></RequireBusinessAccount>} />
        <Route path="resources/calculators/total-comp" element={<RequireBusinessAccount><CalcTotalComp embedded /></RequireBusinessAccount>} />
        <Route path="resources/audit" element={<RequireBusinessAccount><ResourcesComplianceAudit embedded /></RequireBusinessAccount>} />
        <Route path="resources/handbook-audit" element={<RequireBusinessAccount><HandbookGapAnalyzer embedded /></RequireBusinessAccount>} />
        <Route path="resources/handbook-audit/result/:reportId" element={<RequireBusinessAccount><HandbookGapResult embedded /></RequireBusinessAccount>} />
        <Route path="resources/glossary" element={<ResourcesGlossary embedded />} />
        <Route path="resources/glossary/:slug" element={<ResourcesGlossaryTerm embedded />} />
        <Route path="inbox" element={<Inbox />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="settings" element={<UserSettings />} />
      </Route>
    </Routes>
  )
}
