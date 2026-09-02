import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import WorkLayout from '../../work/layout/WorkLayout'
import ChannelBrowse from '../../work/pages/ChannelBrowse'
import ChannelJoinByInvite from '../../work/pages/ChannelJoinByInvite'
import ChannelView from '../../work/pages/ChannelView'
import EventsHub from '../../work/pages/EventsHub'
import InventoryAudit from '../../work/pages/InventoryAudit'
import InventoryHub from '../../work/pages/InventoryHub'
import InventoryForecast from '../../work/pages/InventoryForecast'
import InventoryBuying from '../../work/pages/InventoryBuying'
import InventoryWaste from '../../work/pages/InventoryWaste'
import ProtocolPage from '../../work/pages/ProtocolPage'
import { FeatureGate } from '../../components/shared/FeatureGate'
import EmployeeSchedule from '../../pages/app/employees/EmployeeSchedule'
import OpsHome from '../pages/OpsHome'
import OpsAccess from '../pages/OpsAccess'
import ScheduleEditor from '../pages/ScheduleEditor'
import { WorkSurfaceProvider } from '../../work/routes/WorkSurfaceContext'
import type { ReactNode } from 'react'

function OpsGate({ children }: { children: ReactNode }) {
  return <FeatureGate feature="matcha_ops" label="Matcha Ops" allowPlatformAdmin>{children}</FeatureGate>
}

export default function OpsRoutes() {
  return (
    <WorkSurfaceProvider value="matcha-ops">
      <Routes>
        <Route element={<WorkLayout />}>
          <Route element={<OpsGate><Outlet /></OpsGate>}>
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
              <Route path="inventory/buying" element={<FeatureGate feature="inventory_forecasting" label="Inventory Buying Guidance" allowPlatformAdmin><InventoryBuying /></FeatureGate>} />
              <Route path="inventory/waste" element={<FeatureGate feature="inventory_waste" label="Inventory Waste" allowPlatformAdmin><InventoryWaste /></FeatureGate>} />
              <Route path="inventory/:itemId" element={<InventoryHub />} />
            </Route>
            <Route path="access" element={<OpsAccess />} />
          </Route>
          <Route
            element={
              <FeatureGate feature="employee_schedule" label="Schedule" allowPlatformAdmin>
                <Outlet />
              </FeatureGate>
            }
          >
            <Route
              path="schedule"
              element={<EmployeeSchedule />}
            />
            <Route path="schedule/editor" element={<ScheduleEditor />} />
            <Route
              path="schedule-intelligence"
              element={<Navigate to="/ops/schedule?tab=intelligence" replace />}
            />
          </Route>
        </Route>
      </Routes>
    </WorkSurfaceProvider>
  )
}
