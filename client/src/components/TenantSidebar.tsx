import ClientSidebar from './ClientSidebar'
import IrSidebar from './ir-only/IrSidebar'
import ResourcesFreeSidebar from './resources-free/ResourcesFreeSidebar'
import { useMe } from '../hooks/useMe'
import { isIrOnlyTier, isResourcesFreeTier } from '../utils/tier'

/**
 * Routes the tenant to the right sidebar based on signup tier:
 *  - resources_free → slim Resources nav + upgrade panel
 *  - ir_only_self_serve → slim IR nav (incidents/employees/company)
 *  - else → full ClientSidebar (bespoke, personal, etc.)
 *
 * Defaults to ClientSidebar while /auth/me is in flight to avoid a flash
 * of the wrong layout for the dominant case.
 */
export default function TenantSidebar() {
  const { me, loading } = useMe()
  if (loading) return <ClientSidebar />
  if (isResourcesFreeTier(me?.profile)) return <ResourcesFreeSidebar />
  if (isIrOnlyTier(me?.profile)) return <IrSidebar />
  return <ClientSidebar />
}
