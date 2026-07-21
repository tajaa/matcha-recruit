import { Navigate, useLocation } from 'react-router-dom'
import { useMe } from '../../hooks/useMe'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

interface Props {
  children: React.ReactNode
}

export default function RequireBusinessAccount({ children }: Props) {
  const { me, loading, authFailed } = useMe()
  const location = useLocation()

  if (loading) {
    return (
      <div
        style={{ backgroundColor: BG, color: MUTED, minHeight: '100vh' }}
        className="flex items-center justify-center text-sm"
      >
        Loading…
      </div>
    )
  }

  // Not `!me`: useMe reports a null user for ANY /auth/me failure, so
  // redirecting on that logs a signed-in user out over a transient 502 and
  // discards where they were. Only a real 401/403 (authFailed) means the
  // session is gone. Same fix as AppLayout / RequireRole / WerkLiteRoutes.
  if (authFailed) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  if (!me) {
    return (
      <div
        style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}
        className="flex items-center justify-center px-6 text-center text-sm"
      >
        Could not verify your session. Check your connection and reload.
      </div>
    )
  }

  if (me.user.role !== 'client') {
    return (
      <div
        style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}
        className="flex items-center justify-center px-6"
      >
        <div
          className="max-w-md w-full p-8 rounded-2xl"
          style={{ border: `1px solid ${LINE}` }}
        >
          <h1
            className="text-2xl mb-3"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            Switch to a business account
          </h1>
          <p className="text-sm mb-6" style={{ color: MUTED }}>
            HR resources are reserved for business accounts. You're signed in
            as <strong style={{ color: INK }}>{me.user.role}</strong>.
            Sign in with a business account to access templates,
            calculators, and the compliance audit.
          </p>
          <a
            href="/login"
            className="inline-block px-5 h-10 rounded-full text-sm font-medium leading-10"
            style={{ backgroundColor: INK, color: BG }}
          >
            Sign in
          </a>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
