import { Routes, Route } from 'react-router-dom'
import WorkLayout from '../layouts/WorkLayout'
import MatchaWorkList from '../pages/work/MatchaWorkList'
import MatchaWorkThread from '../pages/work/MatchaWorkThread'
import ProjectView from '../pages/work/ProjectView'
import ChannelView from '../pages/work/ChannelView'
import WorkEmail from '../pages/work/WorkEmail'
import ChannelBrowse from '../pages/work/ChannelBrowse'
import ChannelJoinByInvite from '../pages/work/ChannelJoinByInvite'
import ChannelBilling from '../pages/work/ChannelBilling'
import ConnectionsPanel from '../components/work/ConnectionsPanel'
import Inbox from '../pages/app/Inbox'

export default function WorkRoutes() {
  return (
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
  )
}
