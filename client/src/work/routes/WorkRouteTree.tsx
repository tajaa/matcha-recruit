import { Routes, Route } from 'react-router-dom'
import WorkLayout from '../layout/WorkLayout'
import MatchaWorkList from '../pages/MatchaWorkList'
import MatchaWorkThread from '../pages/MatchaWorkThread'
import ProjectView from '../pages/ProjectView'
import ChannelView from '../pages/ChannelView'
import WorkEmail from '../pages/WorkEmail'
import ChannelBrowse from '../pages/ChannelBrowse'
import ChannelJoinByInvite from '../pages/ChannelJoinByInvite'
import ChannelBilling from '../pages/ChannelBilling'
import ConnectionsPanel from '../components/shell/ConnectionsPanel'
import Inbox from '../pages/Inbox'
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
          <Route path="channels/:channelId" element={<ChannelView />} />
          <Route path=":threadId" element={<MatchaWorkThread />} />
          <Route path="projects/:projectId" element={<ProjectView />} />
        </Route>
      </Routes>
    </WorkSurfaceProvider>
  )
}
