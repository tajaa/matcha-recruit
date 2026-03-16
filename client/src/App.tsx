import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing'
import Login from './pages/Login'
import AppLayout from './layouts/AppLayout'
import AdminSidebar from './components/AdminSidebar'
import ClientSidebar from './components/ClientSidebar'
import Companies from './pages/admin/Companies'
import Features from './pages/admin/Features'
import Settings from './pages/admin/Settings'
import Dashboard from './pages/app/Dashboard'
import Employees from './pages/app/Employees'
import Onboarding from './pages/app/Onboarding'
import ERCopilot from './pages/app/ERCopilot'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/admin" element={<AppLayout sidebar={<AdminSidebar />} />}>
        <Route index element={<Navigate to="companies" replace />} />
        <Route path="companies" element={<Companies />} />
        <Route path="features" element={<Features />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="/app" element={<AppLayout sidebar={<ClientSidebar />} />}>
        <Route index element={<Dashboard />} />
        <Route path="employees" element={<Employees />} />
        <Route path="onboarding" element={<Onboarding />} />
        <Route path="er-copilot" element={<ERCopilot />} />
      </Route>
    </Routes>
  )
}
