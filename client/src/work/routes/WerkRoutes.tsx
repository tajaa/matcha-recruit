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
import { WorkSurfaceProvider } from './WorkSurfaceContext'

// Werk — the personal product surface (role='individual'), served at /werk.
// Reuses the same page components as the business /work tree (WorkRoutes); the
// only difference is the surface value, which drives branding + nav base paths.
export default function WerkRoutes() {
  return (
    <WorkSurfaceProvider value="werk">
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
