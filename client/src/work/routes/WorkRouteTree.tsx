import { Routes, Route, Outlet } from 'react-router-dom'
import WorkLayout from '../layout/WorkLayout'
import MatchaWorkList from '../pages/MatchaWorkList'
import MatchaWorkThread from '../pages/MatchaWorkThread'
import ProjectView from '../pages/ProjectView'
import ChannelView from '../pages/ChannelView'
import LegacyChannelRedirect, { LegacyOpsRedirect } from '../pages/LegacySurfaceRedirect'
import WorkEmail from '../pages/WorkEmail'
import ChannelBrowse from '../pages/ChannelBrowse'
import ChannelJoinByInvite from '../pages/ChannelJoinByInvite'
import ChannelBilling from '../pages/ChannelBilling'
import ConnectionsPanel from '../components/shell/ConnectionsPanel'
import Inbox from '../pages/Inbox'
import EventsHub from '../pages/EventsHub'
import ProtocolPage from '../pages/ProtocolPage'
import InventoryHub from '../pages/InventoryHub'
import InventoryAudit from '../pages/InventoryAudit'
import InventoryForecast from '../pages/InventoryForecast'
import InventoryWaste from '../pages/InventoryWaste'
import InventoryBuying from '../pages/InventoryBuying'
import AssetsHub from '../pages/AssetsHub'
import { FeatureGate } from '../../components/shared/FeatureGate'
import { WorkSurfaceProvider, type WorkSurface } from './WorkSurfaceContext'

// The route tree shared by the two full work surfaces:
//
//   /work  → matcha-work, the business product (role='client', inside a company)
//   /werk  → werk, the personal product (role='individual')
//
// These were two files that differed only in the WorkSurfaceProvider value, so
// every new route had to be added twice — a two-place edit with no compiler
// help if you missed one. The surface value drives branding and nav base paths;
// the routes themselves are identical by design.
//
// NOT merged in: WerkLiteRoutes. It looks similar but is a different tree — its
// own login route, its own auth guard, a `werk_lite` FeatureGate, and a
// deliberately narrower route set (channels + boards, no threads/inbox/email).
// Folding it in here would mean reintroducing all of that as conditionals.
export function WorkRouteTree({ surface }: { surface: WorkSurface }) {
  const businessWork = surface === 'matcha-work'
  return (
    <WorkSurfaceProvider value={surface}>
      <Routes>
        <Route element={<WorkLayout />}>
          <Route index element={<MatchaWorkList />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="email" element={<WorkEmail />} />
          <Route path="billing" element={<ChannelBilling />} />
          <Route path="connections" element={<ConnectionsPanel />} />
          <Route path="channels" element={<ChannelBrowse />} />
          <Route path="channels/join/:code" element={<ChannelJoinByInvite />} />
          <Route path="channels/:channelId" element={businessWork ? <LegacyChannelRedirect communityElement={<ChannelView />} /> : <ChannelView />} />
          <Route
            element={
              businessWork ? <LegacyOpsRedirect fromPrefix="/work" toPrefix="/ops" /> : <FeatureGate feature="ems" label="Ops — Events">
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
              businessWork ? <LegacyOpsRedirect fromPrefix="/work" toPrefix="/ops" /> : <FeatureGate feature="inventory" label="Ops — Inventory">
                <Outlet />
              </FeatureGate>
            }
          >
            <Route path="inventory" element={<InventoryHub />} />
            <Route path="inventory/audit" element={<InventoryAudit />} />
            <Route path="inventory/forecast" element={<FeatureGate feature="inventory_forecasting" label="Inventory Forecasting"><InventoryForecast /></FeatureGate>} />
            <Route path="inventory/buying" element={<FeatureGate feature="inventory_forecasting" label="Inventory Buying Guidance"><InventoryBuying /></FeatureGate>} />
            <Route path="inventory/waste" element={<FeatureGate feature="inventory_waste" label="Inventory Waste"><InventoryWaste /></FeatureGate>} />
            <Route path="inventory/:itemId" element={<InventoryHub />} />
          </Route>
          <Route
            element={
              <FeatureGate feature="huume" label="Huume — Assets">
                <Outlet />
              </FeatureGate>
            }
          >
            <Route path="assets" element={<AssetsHub />} />
            <Route path="assets/:assetId" element={<AssetsHub />} />
          </Route>
          <Route path=":threadId" element={<MatchaWorkThread />} />
          <Route path="projects/:projectId" element={<ProjectView />} />
        </Route>
      </Routes>
    </WorkSurfaceProvider>
  )
}
