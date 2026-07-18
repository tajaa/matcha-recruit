import { Routes, Route } from 'react-router-dom'
import { FeatureGate } from '../components/shared/FeatureGate'
import PortalLayout from '../pages/portal/PortalLayout'
import PortalDashboard from '../pages/portal/PortalDashboard'
import PortalSchedule from '../pages/portal/PortalSchedule'
import EmployeeTakeTraining from '../pages/portal/EmployeeTakeTraining'
import EmployeeSignDocument from '../pages/portal/EmployeeSignDocument'

export default function PortalRoutes() {
  return (
    <Routes>
      <Route element={<PortalLayout />}>
        <Route index element={<PortalDashboard />} />
        <Route
          path="schedule"
          element={
            <FeatureGate feature="employee_schedule" label="My Schedule">
              <PortalSchedule />
            </FeatureGate>
          }
        />
        <Route path="training/:recordId" element={<EmployeeTakeTraining />} />
        <Route path="documents/:documentId" element={<EmployeeSignDocument />} />
      </Route>
    </Routes>
  )
}
