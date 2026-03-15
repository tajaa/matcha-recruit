import { Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Login from './pages/Login'
import AppLayout from './layouts/AppLayout'
import Dashboard from './pages/Dashboard'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/admin" element={<AppLayout />}>
        <Route index element={<Dashboard />} />
      </Route>
    </Routes>
  )
}
