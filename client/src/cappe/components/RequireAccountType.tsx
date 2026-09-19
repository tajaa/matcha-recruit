import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useCappeMe } from '../hooks/useCappeMe'
import { creatorPaths } from '../creators/creatorPaths'

/** Route guard for the creator-marketplace dashboards.
 *
 *  `CappeLayout` only checks that *a* Cappe session exists, so a business
 *  account could land on the creator dashboard and a creator on the brand
 *  side. The pages coped by rendering `return null` after their hooks (a
 *  blank screen) or by showing a form whose POST 403s — both dead ends with
 *  nothing to click. Send the account to its own home instead.
 *
 *  An account that is neither (`personal`) goes to the site list, which has
 *  no account-type guard, so no redirect here can loop. */
export default function RequireAccountType({ type, children }: {
  type: 'creator' | 'business'
  children: ReactNode
}) {
  const { account, loading } = useCappeMe()

  // Same shell CappeLayout shows while /auth/me is in flight, so the guard
  // doesn't flash a second, different spinner underneath it.
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }
  // No account: CappeLayout's own effect is already redirecting to login.
  if (!account) return null
  if (account.account_type === type) return <>{children}</>

  const home = account.account_type === 'creator'
    ? creatorPaths.home
    : account.account_type === 'business'
      ? creatorPaths.brandHome
      : '/cappe/sites'
  return <Navigate replace to={home} />
}
