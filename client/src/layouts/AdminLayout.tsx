import { Outlet, useLocation } from 'react-router-dom'
import { findAdminPage } from '../components/admin/adminNavigation'
import { AdminPageContext } from '../components/admin/AdminPageContext'
import { AdminPageHeader } from '../components/admin/AdminPageHeader'
import { AdminRouteTabs } from '../components/admin/AdminTabs'

/** One centered Settings-style page; related tools are tabs of a workspace. */
export default function AdminLayout() {
  const { pathname } = useLocation()
  const active = findAdminPage(pathname)
  const workspace = active?.page

  return (
    <div className="mx-auto w-full min-w-0 max-w-6xl">
      {active && (
        <div className="mb-8">
          <p className="mb-3 text-xs text-zinc-500">Administration <span className="mx-2 text-zinc-600">/</span> {active.area.label}</p>
          {active.area.pages.length > 1 && <AdminRouteTabs links={active.area.pages} activeTo={active.page.to} label={`${active.area.label} workspaces`} />}
          {workspace?.tabs && <>
            <AdminPageHeader title={workspace.label} description={workspace.description} />
            <AdminRouteTabs links={workspace.tabs} activeTo={active.tab.to} label={`${workspace.label} pages`} />
          </>}
        </div>
      )}
      <AdminPageContext.Provider value={!!workspace?.tabs}>
        <Outlet />
      </AdminPageContext.Provider>
    </div>
  )
}
