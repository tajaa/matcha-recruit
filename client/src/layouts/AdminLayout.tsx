import { Link, Outlet, useLocation } from 'react-router-dom'
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
        <nav aria-label="Breadcrumb" className="mb-6 text-xs text-zinc-500">
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
      )}
      <Outlet />
    </div>
  )
}
