import { Building2, ToggleRight, Settings, MapPin } from 'lucide-react'
import SidebarShell from './SidebarShell'

const nav = [
  { to: '/admin/companies', icon: Building2, label: 'Companies' },
  { to: '/admin/features', icon: ToggleRight, label: 'Business Features' },
  { to: '/admin/jurisdiction-data', icon: MapPin, label: 'Jurisdiction Data' },
  { to: '/admin/settings', icon: Settings, label: 'Settings' },
]

export default function AdminSidebar() {
  return <SidebarShell logoTo="/admin" logoLabel="Matcha Admin" nav={nav} />
}
