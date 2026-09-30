import { Routes, Route, Outlet } from 'react-router-dom'
import WorkLayout from '../layout/WorkLayout'
import MatchaWorkList from '../pages/MatchaWorkList'
import MatchaWorkThread from '../pages/MatchaWorkThread'
import ProjectView from '../pages/ProjectView'
import Journals from '../pages/Journals'
import Productivity from '../pages/Productivity'
import ChannelView from '../pages/ChannelView'
import LegacyChannelRedirect, { LegacySurfacePrefixRedirect } from '../pages/LegacySurfaceRedirect'
import WorkEmail from '../pages/WorkEmail'
import WorkSettings from '../pages/WorkSettings'
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
import Assistant from '../pages/Assistant'
import SymChatList from '../pages/SymChat/SymChatList'
import SymChatDetail from '../pages/SymChat/SymChatDetail'
import Drive from '../pages/Drive'
import HrCases from '../pages/HrCases'
import WriteUps from '../pages/WriteUps'
import { FeatureGate } from '../../components/shared/FeatureGate'
import { WorkSurfaceProvider, type WorkSurface } from './WorkSurfaceContext'

// The route tree shared by the two full work surfaces:
//
//   /work  → matcha-work, the business product (role='client', inside a company)
//   /espresso → Espresso, the personal product (role='individual')
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
          <Route path="settings" element={<WorkSettings />} />
          <Route path="billing" element={<ChannelBilling />} />
          <Route path="connections" element={<ConnectionsPanel />} />
          <Route path="channels" element={<ChannelBrowse />} />
          <Route path="channels/join/:code" element={<ChannelJoinByInvite />} />
          <Route path="channels/:channelId" element={businessWork ? <LegacyChannelRedirect communityElement={<ChannelView />} /> : <ChannelView />} />
          <Route
            element={
              businessWork ? <LegacySurfacePrefixRedirect fromPrefix="/work" toPrefix="/ops" /> : <FeatureGate feature="ems" label="Ops — Events">
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
              businessWork ? <LegacySurfacePrefixRedirect fromPrefix="/work" toPrefix="/ops" /> : <FeatureGate feature="inventory" label="Ops — Inventory">
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
          {/* The Espresso assistant: a private conversation per person, on
              both surfaces. */}
          <Route
            path="assistant"
            element={
              <FeatureGate feature="espresso_assistant" label="Espresso Assistant">
                <Assistant />
              </FeatureGate>
            }
          />
          {/* Sym-chat is business-only: the backend 403s personal workspaces,
              so the /espresso tree doesn't mount it at all. */}
          {businessWork && (
            <Route
              element={
                <FeatureGate feature="sym_chat" label="Sym-chat">
                  <Outlet />
                </FeatureGate>
              }
            >
              <Route path="sym-chat" element={<SymChatList />} />
              <Route path="sym-chat/:chatId" element={<SymChatDetail />} />
            </Route>
          )}
          {/* Drive is business-only too (company + HR document store). */}
          {businessWork && (
            <Route
              element={
                <FeatureGate feature="matcha_drive" label="Drive">
                  <Outlet />
                </FeatureGate>
              }
            >
              <Route path="drive" element={<Drive />} />
              <Route path="drive/:folderId" element={<Drive />} />
            </Route>
          )}
          {/* HR Cases: business-only, HR-only (the page 404s for anyone else). */}
          {businessWork && (
            <Route
              element={
                <FeatureGate feature="hr_cases" label="HR Cases">
                  <Outlet />
                </FeatureGate>
              }
            >
              <Route path="hr-cases" element={<HrCases />} />
              <Route path="hr-cases/:caseId" element={<HrCases />} />
              <Route path="write-ups" element={<WriteUps />} />
              <Route path="write-ups/:caseId" element={<WriteUps />} />
            </Route>
          )}
          <Route path="journals" element={<Journals />} />
          <Route path="journals/:journalId" element={<Journals />} />
          <Route path="productivity" element={<Productivity />} />
          <Route path=":threadId" element={<MatchaWorkThread />} />
          <Route path="projects/:projectId" element={<ProjectView />} />
        </Route>
      </Routes>
    </WorkSurfaceProvider>
  )
}
