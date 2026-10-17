import { Link, Outlet, useLocation } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { ADMIN_AREAS, findAdminPage } from '../components/admin/adminNavigation'

/** Centered Settings-style canvas; every routed tool supplies its own heading. */
export default function AdminLayout() {
  const { pathname } = useLocation()
  const active = findAdminPage(pathname)
  const area = active?.area ?? ADMIN_AREAS.find((area) => area.to === pathname)
  const page = active?.page

  return (
    <div className="mx-auto w-full min-w-0 max-w-6xl">
      {area && (
        <div className={`mb-4 flex flex-wrap items-center justify-between gap-3 ${page && area.to !== page.to ? 'sticky top-14 z-20 rounded-lg border border-zinc-800 bg-zinc-900/95 px-3 py-2 backdrop-blur md:top-2' : ''}`}>
          {page && area.to !== page.to && <Link to={area.to} className="inline-flex items-center gap-2 text-xs font-medium text-zinc-200 hover:text-white"><ArrowLeft size={14} />Back to {area.label}</Link>}
        <nav aria-label="Breadcrumb" className="text-xs text-zinc-500">
          <ol className="flex flex-wrap items-center gap-2">
            <li><Link to="/admin" className="hover:text-zinc-200">Administration</Link></li>
            <li aria-hidden="true" className="text-zinc-600">/</li>
            <li>
              {pathname === area.to
                ? <span aria-current="page">{area.label}</span>
                : <Link to={area.to} className="hover:text-zinc-200">{area.label}</Link>}
            </li>
            {page && page.to !== area.to && <>
              <li aria-hidden="true" className="text-zinc-600">/</li>
              <li>
                {pathname === page.to
                  ? <span aria-current="page" className="text-zinc-300">{page.label}</span>
                  : <Link to={page.to} className="hover:text-zinc-200">{page.label}</Link>}
              </li>
            </>}
          </ol>
        </nav>
        </div>
      )}
      <Outlet />
    </div>
  )
}
