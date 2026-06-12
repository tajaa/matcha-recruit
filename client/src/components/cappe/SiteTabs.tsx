import { NavLink, useParams } from 'react-router-dom'
import { FileText, ShoppingBag, Receipt, Users, Mail, Inbox, Calendar, Newspaper } from 'lucide-react'

const TABS: { to: string; label: string; icon: typeof FileText; end?: boolean }[] = [
  { to: '', label: 'Pages', icon: FileText, end: true },
  { to: 'shop', label: 'Shop', icon: ShoppingBag },
  { to: 'orders', label: 'Orders', icon: Receipt },
  { to: 'subscribers', label: 'Subscribers', icon: Users },
  { to: 'campaigns', label: 'Campaigns', icon: Mail },
  { to: 'forms', label: 'Forms', icon: Inbox },
  { to: 'bookings', label: 'Bookings', icon: Calendar },
  { to: 'blog', label: 'Blog', icon: Newspaper },
]

/** Secondary tab nav across a site's surfaces. Renders at the top of each
 *  site-scoped page. */
export default function SiteTabs() {
  const { siteId } = useParams<{ siteId: string }>()
  const base = `/cappe/sites/${siteId}`
  return (
    <nav className="mb-6 flex flex-wrap gap-1 border-b border-zinc-200">
      {TABS.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to ? `${base}/${to}` : base}
          end={end}
          className={({ isActive }) =>
            `flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? 'border-emerald-600 text-emerald-700'
                : 'border-transparent text-zinc-500 hover:text-zinc-800'
            }`
          }
        >
          <Icon className="h-4 w-4" />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}
