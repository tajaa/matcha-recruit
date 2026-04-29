import ClientSidebar from './ClientSidebar'
import IrSidebar from './ir-only/IrSidebar'
import { useMe } from '../hooks/useMe'
import { isIrOnlyTier } from '../utils/tier'

/**
 * Picks the slim IR-only sidebar for self-serve Matcha IR tenants and
 * the full ClientSidebar for everyone else (bespoke clients, personal
 * accounts, etc.). Defaults to ClientSidebar while /auth/me is in flight
 * to avoid a flash of the wrong layout.
 */
export default function TenantSidebar() {
  const { me, loading } = useMe()
  if (loading) return <ClientSidebar />
  if (isIrOnlyTier(me?.profile)) return <IrSidebar />
  return <ClientSidebar />
}
