import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import WorkLayout from '../../work/layout/WorkLayout'
import ChannelBrowse from '../../work/pages/ChannelBrowse'
import ChannelJoinByInvite from '../../work/pages/ChannelJoinByInvite'
import ChannelView from '../../work/pages/ChannelView'
import EventsHub from '../../work/pages/EventsHub'
import InventoryAudit from '../../work/pages/InventoryAudit'
import InventoryHub from '../../work/pages/InventoryHub'
import InventoryForecast from '../../work/pages/InventoryForecast'
import ProtocolPage from '../../work/pages/ProtocolPage'
import { FeatureGate } from '../../components/shared/FeatureGate'
import EmployeeSchedule from '../../pages/app/employees/EmployeeSchedule'
import OpsHome from '../pages/OpsHome'
import OpsAccess from '../pages/OpsAccess'
import { WorkSurfaceProvider } from '../../work/routes/WorkSurfaceContext'
import type { ReactNode } from 'react'

function OpsGate({ children }: { children: ReactNode }) {
  return <FeatureGate feature="matcha_ops" label="Matcha Ops" allowPlatformAdmin>{children}</FeatureGate>
}

export default function OpsRoutes() {
  return (
    <OpsGate>
      <WorkSurfaceProvider value="matcha-ops">
        <Routes>
          <Route element={<WorkLayout />}>
            <Route index element={<OpsHome />} />
            <Route path="channels" element={<ChannelBrowse />} />
            <Route path="channels/join/:code" element={<ChannelJoinByInvite />} />
            <Route path="channels/:channelId" element={<ChannelView />} />
            <Route
              element={
                <FeatureGate feature="ems" label="Events" allowPlatformAdmin>
                  <Outlet />
                </FeatureGate>
              }
            >
              <Route path="events" element={<EventsHub />} />
              <Route path="events/:eventId" element={<EventsHub />} />
              <Route path="protocol" element={<ProtocolPage />} />
            </Route>
            <Route
              element={
                <FeatureGate feature="inventory" label="Inventory" allowPlatformAdmin>
                  <Outlet />
                </FeatureGate>
              }
            >
              <Route path="inventory" element={<InventoryHub />} />
              <Route path="inventory/audit" element={<InventoryAudit />} />
              <Route path="inventory/forecast" element={<FeatureGate feature="inventory_forecasting" label="Inventory Forecasting" allowPlatformAdmin><InventoryForecast /></FeatureGate>} />
              <Route path="inventory/:itemId" element={<InventoryHub />} />
            </Route>
            <Route
              path="schedule"
              element={
                <FeatureGate feature="employee_schedule" label="Schedule" allowPlatformAdmin>
                  <EmployeeSchedule />
                </FeatureGate>
              }
            />
            <Route
              path="schedule-intelligence"
              element={<Navigate to="/ops/schedule?tab=intelligence" replace />}
            />
            <Route path="access" element={<OpsAccess />} />
          </Route>
        </Routes>
      </WorkSurfaceProvider>
    </OpsGate>
  )
}
