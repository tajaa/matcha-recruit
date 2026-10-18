import { adminSidebarItems } from '../admin/adminNavigation'
import SidebarShell from './SidebarShell'

export default function AdminSidebar() {
  return <SidebarShell logoTo="/admin" logoLabel="Matcha Admin" nav={adminSidebarItems()} footerSlot={null} />
}
