import { Navigate, Route, Routes } from 'react-router-dom'
import { useEffect } from 'react'
import RequireRole from '../components/auth/RequireRole'
import GummfitAdminLayout from '../layouts/GummfitAdminLayout'
import Login from '../pages/Login'
import Cappe from '../pages/admin/customers/workspaces/Cappe'
import GummfitModels from '../pages/admin/platform/GummfitModels'
import { GUMMFIT_ADMIN_PATH } from '../api/authPaths'

// Staff use Matcha admin credentials. Cappe's customer session never grants
// access to these tools; every existing API still enforces require_admin.
export default function GummfitAdminRoutes() {
  useEffect(() => {
    const title = document.title
    document.title = 'Gummfit Admin'
    return () => { document.title = title }
  }, [])

  return (
    <Routes>
      <Route path="login" element={<Login surface="gummfit-admin" />} />
      <Route element={<RequireRole roles={['admin']}><GummfitAdminLayout /></RequireRole>}>
        <Route index element={<Cappe />} />
        <Route path="models" element={<GummfitModels />} />
        <Route path="*" element={<Navigate to={GUMMFIT_ADMIN_PATH} replace />} />
      </Route>
    </Routes>
  )
}
