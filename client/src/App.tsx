import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing'
import Login from './pages/Login'
import AppLayout from './layouts/AppLayout'
import AdminSidebar from './components/AdminSidebar'
import ClientSidebar from './components/ClientSidebar'
import Companies from './pages/admin/Companies'
import Features from './pages/admin/Features'
import Settings from './pages/admin/Settings'
import JurisdictionData from './pages/admin/JurisdictionData'
import Jurisdictions from './pages/admin/Jurisdictions'
import Dashboard from './pages/app/Dashboard'
import Employees from './pages/app/Employees'
import Onboarding from './pages/app/Onboarding'
import ERCopilot from './pages/app/ERCopilot'
import ERCaseDetail from './pages/app/ERCaseDetail'
import Compliance from './pages/app/Compliance'
import EmployeeDetail from './pages/app/EmployeeDetail'
import IRList from './pages/app/IRList'
import IRDetail from './pages/app/IRDetail'
import Handbooks from './pages/app/Handbooks'
import HandbookDetail from './pages/app/HandbookDetail'
import HandbookForm from './pages/app/HandbookForm'
import RiskAssessment from './pages/app/RiskAssessment'
import ERExportDownload from './pages/shared/ERExportDownload'
import WorkLayout from './layouts/WorkLayout'
import MatchaWorkList from './pages/work/MatchaWorkList'
import MatchaWorkThread from './pages/work/MatchaWorkThread'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/s/:token" element={<ERExportDownload />} />
      <Route path="/work" element={<WorkLayout />}>
        <Route index element={<MatchaWorkList />} />
        <Route path=":threadId" element={<MatchaWorkThread />} />
      </Route>
      <Route path="/admin" element={<AppLayout sidebar={<AdminSidebar />} />}>
        <Route index element={<Navigate to="companies" replace />} />
        <Route path="companies" element={<Companies />} />
        <Route path="features" element={<Features />} />
        <Route path="settings" element={<Settings />} />
        <Route path="jurisdiction-data" element={<JurisdictionData />} />
        <Route path="jurisdictions" element={<Jurisdictions />} />
      </Route>
      <Route path="/app" element={<AppLayout sidebar={<ClientSidebar />} />}>
        <Route index element={<Dashboard />} />
        <Route path="employees" element={<Employees />} />
        <Route path="employees/:employeeId" element={<EmployeeDetail />} />
        <Route path="onboarding" element={<Onboarding />} />
        <Route path="er-copilot" element={<ERCopilot />} />
        <Route path="er-copilot/:caseId" element={<ERCaseDetail />} />
        <Route path="compliance" element={<Compliance />} />
        <Route path="ir" element={<IRList />} />
        <Route path="ir/:incidentId" element={<IRDetail />} />
        <Route path="handbooks" element={<Handbooks />} />
        <Route path="handbook/new" element={<HandbookForm />} />
        <Route path="handbook/:id" element={<HandbookDetail />} />
        <Route path="handbook/:id/edit" element={<HandbookForm />} />
        <Route path="risk-assessment" element={<RiskAssessment />} />
      </Route>
    </Routes>
  )
}
