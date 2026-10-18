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
    <nav aria-label={`${area.label} tools`} className="admin-directory grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {area.pages.map((page) => (
        <Link key={page.to} to={page.to} aria-label={page.label} className="group rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400">
          <AdminCard className="h-full transition-colors">
            <div className="mb-4 flex items-center justify-between">
              <page.icon className="h-5 w-5 text-zinc-400" strokeWidth={1.5} aria-hidden="true" />
              <ArrowRight className="h-4 w-4 text-zinc-600 transition-colors group-hover:text-zinc-200" aria-hidden="true" />
            </div>
            <h2 className="text-sm font-medium text-zinc-100">{page.label}</h2>
            <p className="mt-2 text-xs leading-relaxed text-zinc-500">{page.description}</p>
          </AdminCard>
        </Link>
      ))}
    </nav>
  </>
}
