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
  const { me, loading } = useMe()
  const location = useLocation()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-sm text-zinc-500">
        Loading…
      </div>
    )
  }

  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  if (!roles.includes(me.user.role)) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
