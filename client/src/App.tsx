import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing'
import Login from './pages/Login'
import AppLayout from './layouts/AppLayout'
import Companies from './pages/admin/Companies'
import Features from './pages/admin/Features'
import Settings from './pages/admin/Settings'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/admin" element={<AppLayout />}>
        <Route index element={<Navigate to="companies" replace />} />
        <Route path="companies" element={<Companies />} />
        <Route path="features" element={<Features />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
