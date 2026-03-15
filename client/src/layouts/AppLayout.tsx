import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

export default function AppLayout() {
  return (
    <div className="min-h-screen bg-zinc-950">
      <Sidebar />
      <main className="ml-56 p-8">
        <Outlet />
      </main>
    </div>
  )
}
