import { Link, Outlet, useLocation } from 'react-router-dom'
import { findAdminPage } from '../components/admin/adminNavigation'

/** Settings' centered canvas, shared by every admin route. */
export default function AdminLayout() {
  const { pathname } = useLocation()
  const active = findAdminPage(pathname)

  return (
    <div className="mx-auto w-full min-w-0 max-w-6xl">
      {active && (
        <div className="mb-8 space-y-3">
          <p className="text-xs text-zinc-500">Administration <span className="mx-2 text-zinc-600">/</span> {active.area.label}</p>
          {active.area.pages.length > 1 && (
            <nav aria-label={`${active.area.label} pages`} className="flex flex-wrap gap-x-5 gap-y-1 border-b border-zinc-700/60">
              {active.area.pages.map((page) => {
                const selected = page === active.page
                return (
                  <Link
                    key={page.to}
                    to={page.to}
                    aria-current={selected ? 'page' : undefined}
                    className={`-mb-px border-b-2 py-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                      selected ? 'border-emerald-500 font-medium text-zinc-100' : 'border-transparent text-zinc-400 hover:border-zinc-500 hover:text-zinc-100'
                    }`}
                  >
                    {page.label}
                  </Link>
                )
              })}
            </nav>
          )}
        </div>
      )}
      <Outlet />
    </div>
  )
}
