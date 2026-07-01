import { Building2, ToggleRight, Settings, MapPin, Globe, ClipboardList, Microscope, FileText, Briefcase, ShieldCheck, Mail, Image as ImageIcon, AlertOctagon, AlertTriangle, BookOpen, Users, Sparkles, Leaf, Calculator, HeartHandshake, LayoutTemplate, Rocket, Database } from 'lucide-react'
import SidebarShell, { type NavGroup } from './SidebarShell'

// Grouped master-admin nav. SidebarShell renders each group as a collapsible
// section (auto-opens when a child route is active), so related tabs stay
// together instead of one long flat list.
const nav: NavGroup[] = [
  {
    defaultOpen: true,
    label: "What's New",
    items: [
      { to: '/admin/updates', icon: Rocket, label: 'Updates' },
    ],
  },
  {
    defaultOpen: true,
    label: 'Customers',
    items: [
      { to: '/admin/customers', icon: Users, label: 'Customers' },
      { to: '/admin/companies', icon: Building2, label: 'Companies' },
      { to: '/admin/matcha-work', icon: Sparkles, label: 'Matcha-Work' },
      { to: '/admin/cappe', icon: LayoutTemplate, label: 'Cappe' },
      { to: '/admin/brokers', icon: Briefcase, label: 'Brokers' },
      { to: '/admin/fractional-hr', icon: HeartHandshake, label: 'Fractional HR' },
    ],
  },
  {
    defaultOpen: true,
    label: 'Sales',
    items: [
      { to: '/admin/gap-analysis', icon: Sparkles, label: 'Gap Analysis' },
      { to: '/admin/deal-flow', icon: Calculator, label: 'Deal Flow' },
      { to: '/admin/matcha-lite', icon: Leaf, label: 'Signup Links' },
    ],
  },
  {
    defaultOpen: true,
    label: 'Compliance Data',
    items: [
      { to: '/admin/compliance-mgmt', icon: ShieldCheck, label: 'Compliance Mgmt' },
      { to: '/admin/jurisdictions', icon: Globe, label: 'Jurisdictions' },
      { to: '/admin/jurisdiction-data', icon: MapPin, label: 'Jurisdiction Data' },
      { to: '/admin/payer-data', icon: FileText, label: 'Payer Data' },
      { to: '/admin/industry-requirements', icon: ClipboardList, label: 'Industry Reqs' },
      { to: '/admin/specialization-research', icon: Microscope, label: 'Specialty Research' },
      { to: '/admin/wc-rate-data', icon: Database, label: 'WC Rate Data' },
    ],
  },
  {
    defaultOpen: true,
    label: 'Marketing',
    items: [
      { to: '/admin/blogs', icon: BookOpen, label: 'Blog' },
      { to: '/admin/newsletter', icon: Mail, label: 'Newsletter' },
      { to: '/admin/landing-media', icon: ImageIcon, label: 'Landing Media' },
    ],
  },
  {
    defaultOpen: true,
    label: 'Monitoring',
    items: [
      { to: '/admin/client-errors', icon: AlertOctagon, label: 'Client Errors' },
      { to: '/admin/server-errors', icon: AlertTriangle, label: 'Server Errors' },
    ],
  },
  {
    defaultOpen: true,
    label: 'Platform',
    items: [
      { to: '/admin/features', icon: ToggleRight, label: 'Business Features' },
      { to: '/admin/settings', icon: Settings, label: 'Settings' },
    ],
  },
]

export default function AdminSidebar() {
  return <SidebarShell logoTo="/admin" logoLabel="Matcha Admin" nav={nav} />
}
