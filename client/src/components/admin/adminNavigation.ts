import { Activity, Boxes, Megaphone, Rocket, Settings, ShieldCheck, Users } from 'lucide-react'
import type { NavIcon, NavItem } from '../sidebars/SidebarShell'

type AdminTabLink = { to: string; label: string }
type AdminWorkspaceLink = AdminTabLink & { description?: string; tabs?: AdminTabLink[] }
type AdminArea = { label: string; icon: NavIcon; pages: AdminWorkspaceLink[] }

// Areas contain workspaces, not a second flat list of every tool. Workspace
// tabs retain their original URLs so bookmarks, composers and detail links work.
export const ADMIN_AREAS: AdminArea[] = [
  {
    label: 'Customers', icon: Users,
    pages: [
      {
        to: '/admin/customers', label: 'Accounts',
        description: 'Customer lifecycle, business approvals, test accounts, and feature access.',
        tabs: [
          { to: '/admin/customers', label: 'Customers' },
          { to: '/admin/companies', label: 'Businesses' },
          { to: '/admin/test-accounts', label: 'Test accounts' },
          { to: '/admin/features', label: 'Feature access' },
        ],
      },
      {
        to: '/admin/matcha-work', label: 'Product workspaces',
        description: 'Manage Matcha Work, operations, and Gummfit accounts in one place.',
        tabs: [
          { to: '/admin/matcha-work', label: 'Matcha Work' },
          { to: '/admin/matcha-ops', label: 'Matcha Ops' },
          { to: '/admin/cappe', label: 'Gummfit' },
          { to: '/admin/cappe-creators', label: 'Creators' },
        ],
      },
      { to: '/admin/fractional-hr', label: 'Fractional HR' },
    ],
  },
  {
    label: 'Products & sales', icon: Boxes,
    pages: [
      {
        to: '/admin/products', label: 'Catalog',
        description: 'Product bundles, checkout pricing, and customer signup links.',
        tabs: [
          { to: '/admin/products', label: 'Products' },
          { to: '/admin/pricing', label: 'Pricing' },
          { to: '/admin/matcha-lite', label: 'Signup links' },
        ],
      },
      { to: '/admin/gap-analysis', label: 'Gap analysis' },
      { to: '/admin/deal-flow', label: 'Deal flow' },
    ],
  },
  {
    label: 'Compliance', icon: ShieldCheck,
    pages: [
      {
        to: '/admin/studio', label: 'Compliance data',
        description: 'Research, maintain, and validate the shared compliance catalog.',
        tabs: [
          { to: '/admin/studio', label: 'Studio' },
          { to: '/admin/jurisdiction-data', label: 'Data quality & policies' },
        ],
      },
      { to: '/admin/compliance-mgmt', label: 'Company compliance' },
      {
        to: '/admin/payer-data', label: 'Reference data',
        description: 'Payer coverage policies and workers’ compensation rate sources.',
        tabs: [
          { to: '/admin/payer-data', label: 'Payers' },
          { to: '/admin/wc-rate-data', label: 'WC rates' },
        ],
      },
    ],
  },
  {
    label: 'Marketing', icon: Megaphone,
    pages: [{
      to: '/admin/blogs', label: 'Content',
      description: 'Publish articles, manage newsletters, and configure landing media.',
      tabs: [
        { to: '/admin/blogs', label: 'Blog' },
        { to: '/admin/newsletter', label: 'Newsletter' },
        { to: '/admin/landing-media', label: 'Landing media' },
      ],
    }],
  },
  {
    label: 'Monitoring', icon: Activity,
    pages: [
      {
        to: '/admin/usage', label: 'Analytics',
        description: 'Product activity, site traffic, and AI consumption.',
        tabs: [
          { to: '/admin/usage', label: 'Product usage' },
          { to: '/admin/traffic', label: 'Site traffic' },
          { to: '/admin/ai-usage', label: 'AI usage' },
        ],
      },
      {
        to: '/admin/server-errors', label: 'Errors',
        description: 'Investigate browser and backend errors, inspect reports, and track resolution.',
        tabs: [
          { to: '/admin/server-errors', label: 'Server' },
          { to: '/admin/client-errors', label: 'Browser' },
        ],
      },
    ],
  },
  {
    label: 'Platform', icon: Settings,
    pages: [
      { to: '/admin/settings', label: 'Settings' },
      { to: '/admin/automation', label: 'Automation' },
    ],
  },
  { label: 'Updates', icon: Rocket, pages: [{ to: '/admin/updates', label: 'Updates' }] },
]

export function findAdminPage(pathname: string): { area: AdminArea; page: AdminWorkspaceLink; tab: AdminTabLink } | undefined {
  return ADMIN_AREAS.flatMap((area) => area.pages.flatMap((page) =>
    (page.tabs ?? [page]).map((tab) => ({ area, page, tab })),
  ))
    .filter(({ tab }) => pathname === tab.to || pathname.startsWith(`${tab.to}/`))
    .sort((a, b) => b.tab.to.length - a.tab.to.length)[0]
}

export function adminSidebarItems(pathname: string): NavItem[] {
  const active = findAdminPage(pathname)
  return ADMIN_AREAS.map((area) => ({
    label: area.label,
    icon: area.icon,
    to: active?.area === area ? active.tab.to : area.pages[0].to,
  }))
}
