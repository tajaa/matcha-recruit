import { Routes, Route } from 'react-router-dom'
import PortalLayout from '../pages/portal/PortalLayout'
import PortalDashboard from '../pages/portal/PortalDashboard'
import EmployeeTakeTraining from '../pages/portal/EmployeeTakeTraining'

export default function PortalRoutes() {
  return (
    <Routes>
      <Route element={<PortalLayout />}>
        <Route index element={<PortalDashboard />} />
        <Route path="training/:recordId" element={<EmployeeTakeTraining />} />
      </Route>
    </Routes>
  )
}
