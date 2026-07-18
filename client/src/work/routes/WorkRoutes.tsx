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

// Matcha-Work — the business product surface (role='client', inside a Matcha
// company), served at /work. Shares the same page components as the personal
// Werk tree (WerkRoutes); only the surface value differs.
export default function WorkRoutes() {
  return (
    <WorkSurfaceProvider value="matcha-work">
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
