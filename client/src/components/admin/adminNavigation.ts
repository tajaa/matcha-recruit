import { Activity, Boxes, Megaphone, Rocket, Settings, ShieldCheck, Users } from 'lucide-react'
import type { NavIcon, NavItem } from '../sidebars/SidebarShell'

type AdminPageLink = { to: string; label: string }
type AdminArea = { label: string; icon: NavIcon; pages: AdminPageLink[] }

// One index for the sidebar and the page-level navigation. Existing URLs stay
// bookmarkable; the rail shows areas, and each area exposes its own pages.
export const ADMIN_AREAS: AdminArea[] = [
  {
    label: 'Customers', icon: Users,
    pages: [
      { to: '/admin/customers', label: 'Customers' },
      { to: '/admin/companies', label: 'Companies' },
      { to: '/admin/test-accounts', label: 'Test accounts' },
      { to: '/admin/matcha-work', label: 'Matcha Work' },
      { to: '/admin/matcha-ops', label: 'Matcha Ops' },
      { to: '/admin/cappe', label: 'Gummfit' },
      { to: '/admin/cappe-creators', label: 'Gummfit creators' },
      { to: '/admin/fractional-hr', label: 'Fractional HR' },
    ],
  },
  {
    label: 'Products & sales', icon: Boxes,
    pages: [
      { to: '/admin/products', label: 'Products' },
      { to: '/admin/pricing', label: 'Pricing' },
      { to: '/admin/matcha-lite', label: 'Signup links' },
      { to: '/admin/gap-analysis', label: 'Gap analysis' },
      { to: '/admin/deal-flow', label: 'Deal flow' },
    ],
  },
  {
    label: 'Compliance', icon: ShieldCheck,
    pages: [
      { to: '/admin/studio', label: 'Studio' },
      { to: '/admin/jurisdiction-data', label: 'Library' },
      { to: '/admin/compliance-mgmt', label: 'Company compliance' },
      { to: '/admin/payer-data', label: 'Payer data' },
      { to: '/admin/wc-rate-data', label: 'WC rates' },
      { to: '/admin/automation', label: 'Automation' },
    ],
  },
  {
    label: 'Marketing', icon: Megaphone,
    pages: [
      { to: '/admin/blogs', label: 'Blog' },
      { to: '/admin/newsletter', label: 'Newsletter' },
      { to: '/admin/landing-media', label: 'Landing media' },
    ],
  },
  {
    label: 'Monitoring', icon: Activity,
    pages: [
      { to: '/admin/traffic', label: 'Traffic' },
      { to: '/admin/usage', label: 'Usage' },
      { to: '/admin/ai-usage', label: 'AI usage' },
      { to: '/admin/client-errors', label: 'Client errors' },
      { to: '/admin/server-errors', label: 'Server errors' },
    ],
  },
  {
    label: 'Platform', icon: Settings,
    pages: [
      { to: '/admin/settings', label: 'Settings' },
      { to: '/admin/features', label: 'Business features' },
    ],
  },
  { label: 'Updates', icon: Rocket, pages: [{ to: '/admin/updates', label: 'Updates' }] },
]

export function findAdminPage(pathname: string): { area: AdminArea; page: AdminPageLink } | undefined {
  return ADMIN_AREAS.flatMap((area) => area.pages.map((page) => ({ area, page })))
    .filter(({ page }) => pathname === page.to || pathname.startsWith(`${page.to}/`))
    .sort((a, b) => b.page.to.length - a.page.to.length)[0]
}

export function adminSidebarItems(pathname: string): NavItem[] {
  const active = findAdminPage(pathname)
  return ADMIN_AREAS.map((area) => ({
    label: area.label,
    icon: area.icon,
    // Keep the active area's link on its current page. This lets SidebarShell
    // retain its existing selection, nested-route, and collapsed-rail behavior.
    to: active?.area === area ? active.page.to : area.pages[0].to,
  }))
}
