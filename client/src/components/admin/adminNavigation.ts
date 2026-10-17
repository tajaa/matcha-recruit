import {
  Activity, AlertOctagon, AlertTriangle, BarChart3, BookOpen, Boxes, Building2,
  Calculator, Cog, Cpu, Database, DollarSign, FileText, HeartHandshake,
  Image as ImageIcon, LayoutTemplate, Leaf, Mail, Megaphone, Radio, Rocket,
  Settings, ShieldCheck, Sparkles, ToggleRight, Users,
} from 'lucide-react'
import type { NavIcon, NavItem } from '../sidebars/SidebarShell'

type AdminPageLink = { to: string; label: string; description: string; icon: NavIcon }
export type AdminArea = AdminPageLink & { pages: AdminPageLink[] }

// Categories are directories, and every tool remains its own page. This one
// inventory drives the sidebar, directory cards, and tool breadcrumbs.
export const ADMIN_AREAS: AdminArea[] = [
  {
    to: '/admin/areas/customers', label: 'Customers', icon: Users,
    description: 'Manage customers, companies, and accounts across each product.',
    pages: [
      { to: '/admin/customers', label: 'Customers', icon: Users, description: 'Review customer accounts, registrations, and onboarding.' },
      { to: '/admin/companies', label: 'Companies', icon: Building2, description: 'Manage businesses, approvals, and company details.' },
      { to: '/admin/test-accounts', label: 'Test Accounts', icon: ShieldCheck, description: 'Create and manage test customers and companies.' },
      { to: '/admin/matcha-work', label: 'Matcha Work', icon: Sparkles, description: 'Manage personal and business AI workspace accounts.' },
      { to: '/admin/matcha-ops', label: 'Matcha Ops', icon: Radio, description: 'Manage operations accounts and product access.' },
      { to: '/admin/cappe', label: 'Cappe', icon: LayoutTemplate, description: 'Manage Gummfit websites, brands, and marketplace activity.' },
      { to: '/admin/cappe-creators', label: 'Gummfit Creators', icon: Users, description: 'Review creator applications, social accounts, and payouts.' },
      { to: '/admin/fractional-hr', label: 'Fractional HR', icon: HeartHandshake, description: 'Manage fractional HR clients and their service workspaces.' },
    ],
  },
  {
    to: '/admin/areas/products-sales', label: 'Products & sales', icon: Boxes,
    description: 'Configure products and pricing, create signup links, and manage sales.',
    pages: [
      { to: '/admin/products', label: 'Products', icon: Boxes, description: 'Build product bundles, features, and signup experiences.' },
      { to: '/admin/pricing', label: 'Pricing', icon: DollarSign, description: 'Set product prices, add-ons, and subscription plans.' },
      { to: '/admin/matcha-lite', label: 'Signup Links', icon: Leaf, description: 'Create customer invitations and bespoke signup links.' },
      { to: '/admin/gap-analysis', label: 'Gap Analysis', icon: Sparkles, description: 'Run company assessments and review compliance gaps.' },
      { to: '/admin/deal-flow', label: 'Deal Flow', icon: Calculator, description: 'Manage sales opportunities, proposals, and deal progress.' },
    ],
  },
  {
    to: '/admin/areas/compliance', label: 'Compliance', icon: ShieldCheck,
    description: 'Manage company compliance and maintain the shared research and reference data.',
    pages: [
      { to: '/admin/compliance-mgmt', label: 'Compliance Management', icon: ShieldCheck, description: 'Manage company locations and compliance requirements.' },
      { to: '/admin/studio', label: 'Compliance Studio', icon: Sparkles, description: 'Research jurisdictions, maintain coverage, and run evaluations.' },
      { to: '/admin/jurisdiction-data', label: 'Compliance Library', icon: BookOpen, description: 'Browse policies, categories, sources, and data quality.' },
      { to: '/admin/payer-data', label: 'Payer Data', icon: FileText, description: 'Maintain payer coverage policies and source documents.' },
      { to: '/admin/wc-rate-data', label: 'WC Rate Data', icon: Database, description: 'Maintain workers’ compensation rates and reference sources.' },
    ],
  },
  {
    to: '/admin/areas/marketing', label: 'Marketing', icon: Megaphone,
    description: 'Publish articles, send newsletters, and manage public-facing media.',
    pages: [
      { to: '/admin/blogs', label: 'Blog', icon: BookOpen, description: 'Write, edit, and publish blog articles.' },
      { to: '/admin/newsletter', label: 'Newsletter', icon: Mail, description: 'Create campaigns, manage subscribers, and review delivery.' },
      { to: '/admin/landing-media', label: 'Landing Media', icon: ImageIcon, description: 'Manage the images and videos used on landing pages.' },
    ],
  },
  {
    to: '/admin/areas/monitoring', label: 'Monitoring', icon: Activity,
    description: 'Review traffic and usage, track AI consumption, and investigate errors.',
    pages: [
      { to: '/admin/traffic', label: 'Traffic', icon: BarChart3, description: 'Review site visits, traffic sources, and visitor activity.' },
      { to: '/admin/usage', label: 'Usage', icon: Activity, description: 'Monitor product activity and customer usage.' },
      { to: '/admin/ai-usage', label: 'AI Usage', icon: Cpu, description: 'Track model activity, token consumption, and AI costs.' },
      { to: '/admin/client-errors', label: 'Client Errors', icon: AlertOctagon, description: 'Investigate browser error reports and track resolution.' },
      { to: '/admin/server-errors', label: 'Server Errors', icon: AlertTriangle, description: 'Investigate backend failures and track resolution.' },
    ],
  },
  {
    to: '/admin/areas/platform', label: 'Platform', icon: Settings,
    description: 'Configure the platform, manage business features, and monitor automation.',
    pages: [
      { to: '/admin/features', label: 'Business Features', icon: ToggleRight, description: 'Manage company feature access, grants, and beta availability.' },
      { to: '/admin/settings', label: 'Settings', icon: Settings, description: 'Configure models, integrations, and platform-wide defaults.' },
      { to: '/admin/automation', label: 'Automation', icon: Cog, description: 'Manage scheduled jobs and inspect their recent runs.' },
    ],
  },
  {
    to: '/admin/updates', label: 'Updates', icon: Rocket,
    description: 'Recent product changes and platform updates.',
    pages: [{ to: '/admin/updates', label: 'Updates', icon: Rocket, description: 'Read recent product changes and platform updates.' }],
  },
]

export function findAdminPage(pathname: string): { area: AdminArea; page: AdminPageLink } | undefined {
  return ADMIN_AREAS.flatMap((area) => area.pages.map((page) => ({ area, page })))
    .filter(({ page }) => pathname === page.to || pathname.startsWith(`${page.to}/`))
    .sort((a, b) => b.page.to.length - a.page.to.length)[0]
}

export function adminSidebarItems(): NavItem[] {
  return ADMIN_AREAS.map((area) => ({
    label: area.label,
    icon: area.icon,
    to: area.to,
    activePaths: area.pages.map((page) => page.to),
  }))
}
