import { useLocation } from 'react-router-dom'
import { adminSidebarItems } from '../admin/adminNavigation'
import SidebarShell from './SidebarShell'

export default function AdminSidebar() {
  const { pathname } = useLocation()
  return <SidebarShell logoTo="/admin" logoLabel="Matcha Admin" nav={adminSidebarItems(pathname)} />
}
