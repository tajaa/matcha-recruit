import { ArrowRight } from 'lucide-react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { ADMIN_AREAS } from '../../components/admin/adminNavigation'
import { AdminPageHeader } from '../../components/admin/AdminPageHeader'
import { AdminCard } from '../../components/admin/AdminUI'

export default function AdminCategoryPage() {
  const { category } = useParams()
  const area = ADMIN_AREAS.find((area) => area.to === `/admin/areas/${category}`)
  if (!area) return <Navigate to={ADMIN_AREAS[0].to} replace />

  return <>
    <AdminPageHeader title={area.label} description={area.description} />
    <nav aria-label={`${area.label} tools`} className="admin-directory grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
      {area.pages.map((page) => (
        <Link key={page.to} to={page.to} aria-label={page.label} className="group rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400">
          <AdminCard className="flex h-full items-center gap-3 transition-colors">
            <page.icon className="h-4 w-4 shrink-0 text-zinc-400" strokeWidth={1.5} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <h2 className="text-xs font-medium text-zinc-100">{page.label}</h2>
              <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">{page.description}</p>
            </div>
            <ArrowRight className="h-3.5 w-3.5 shrink-0 text-zinc-500 transition-colors group-hover:text-zinc-200" aria-hidden="true" />
          </AdminCard>
        </Link>
      ))}
    </nav>
  </>
}
