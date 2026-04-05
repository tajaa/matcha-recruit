import { Building2, ToggleRight, Settings, MapPin, Globe, ClipboardList, Microscope, FileText, Briefcase, ShieldCheck, User } from 'lucide-react'
import SidebarShell from './SidebarShell'

const nav = [
  { to: '/admin/companies', icon: Building2, label: 'Companies' },
  { to: '/admin/individuals', icon: User, label: 'Individuals' },
  { to: '/admin/brokers', icon: Briefcase, label: 'Brokers' },
  { to: '/admin/features', icon: ToggleRight, label: 'Business Features' },
  { to: '/admin/compliance-mgmt', icon: ShieldCheck, label: 'Compliance Mgmt' },
  { to: '/admin/jurisdictions', icon: Globe, label: 'Jurisdictions' },
  { to: '/admin/jurisdiction-data', icon: MapPin, label: 'Jurisdiction Data' },
  { to: '/admin/payer-data', icon: FileText, label: 'Payer Data' },
  { to: '/admin/industry-requirements', icon: ClipboardList, label: 'Industry Reqs' },
  { to: '/admin/specialization-research', icon: Microscope, label: 'Specialty Research' },
  { to: '/admin/settings', icon: Settings, label: 'Settings' },
]

export default function AdminSidebar() {
  return <SidebarShell logoTo="/admin" logoLabel="Matcha Admin" nav={nav} />
}
