import { Navigate, useLocation } from 'react-router-dom'
import { useMe } from '../../hooks/useMe'

interface Props {
  /** Roles allowed to render the subtree. Anything else is bounced. */
  roles: string[]
  children: React.ReactNode
}

/**
 * Client-side role gate for whole route trees (/admin, /broker). Not a
 * security boundary — the backend enforces authz — but it stops other roles
 * from mounting the shell and probing every endpoint with their token.
 * Fail-closed: missing user or missing role never renders children.
 */
export default function RequireRole({ roles, children }: Props) {
  const { me, loading, authFailed } = useMe()
  const location = useLocation()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-sm text-zinc-500">
        Loading…
      </div>
    )
  }

  // Only a real 401/403 sends the user to login. `me === null` also covers "the
  // /auth/me call failed" (5xx, network drop), and bouncing on that logs out a
  // signed-in admin over a transient blip — see isNoSession in hooks/useMe.
  if (authFailed) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  // Still fail closed when we simply don't know who this is: render nothing
  // rather than the shell. Unlike the redirect, this is recoverable — a retry
  // or navigation re-runs the lookup without discarding the user's location.
  if (!me) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-sm text-zinc-500">
        Could not verify your session. Check your connection and reload.
      </div>
    )
  }

  if (!roles.includes(me.user.role)) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
